import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import uuid

from PIL import Image
from pypdf import PdfReader

from mcp_client import Client, ProtocolError, ToolError, UncertainMutation
from mcp_face_dimension_smoke import request, save_verified
from mcp_isolated_smoke import read_state


def ink_components(path):
    image = Image.open(path).convert('L')
    dark = {(index % image.width, index // image.width)
            for index, value in enumerate(image.tobytes()) if value < 120}
    found = []
    while dark:
        first = dark.pop()
        stack = [first]
        min_x = max_x = first[0]
        min_y = max_y = first[1]
        area = 0
        while stack:
            x, y = stack.pop()
            area += 1
            min_x, max_x = min(min_x, x), max(max_x, x)
            min_y, max_y = min(min_y, y), max(max_y, y)
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    neighbor = (x + dx, y + dy)
                    if neighbor in dark:
                        dark.remove(neighbor)
                        stack.append(neighbor)
        if area > 2:
            found.append([min_x, min_y, max_x-min_x+1, max_y-min_y+1, area])
    return found

def main():
    repo = Path(__file__).resolve().parents[2]
    server = Path(sys.argv[1] if len(sys.argv) > 1 else repo / 'target' / 'debug' / 'OpenCADStudio.exe').resolve()
    pen_widths = len(sys.argv) > 2 and sys.argv[2] == '--pen-widths'
    bylayer_weights = len(sys.argv) > 2 and sys.argv[2] == '--bylayer-weights'
    if len(sys.argv) > 2 and not (pen_widths or bylayer_weights):
        raise ValueError('Only --pen-widths or --bylayer-weights is supported')
    width_qa = pen_widths or bylayer_weights
    if not server.is_file():
        raise FileNotFoundError(server)
    out = repo / 'target' / 'mcp-isolated' / (time.strftime('%Y%m%d-%H%M%S') + '-metric-content-' + uuid.uuid4().hex[:8])
    out.mkdir()
    profile = out / 'profile'; profile.mkdir()
    temporary = out / 'temp'; temporary.mkdir()
    env = os.environ.copy(); env.update({'APPDATA':str(profile),'LOCALAPPDATA':str(profile),'TEMP':str(temporary),'TMP':str(temporary)})
    gui = subprocess.Popen([str(server),'--new-instance'],cwd=repo,env=env,stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    client=Client(server,environment=env)
    report={'schema_version':'mcp-metric-bylayer-l2-1' if bylayer_weights else
            'mcp-metric-pen-l2-1' if pen_widths else 'mcp-metric-content-l2-1',
            'status':'failed','output':str(out),
            'binary_sha256':hashlib.sha256(server.read_bytes()).hexdigest().upper()}
    try:
        client.handshake()
        chosen=client.ready_session(wait_for_existing=True,timeout=90)
        session=chosen['session_id']
        if chosen['process_id'] != gui.pid or Path(chosen['executable_path']).resolve() != server:
            raise ProtocolError('Isolated GUI identity differs')
        report['session']={'id':session,'pid':gui.pid}
        state=read_state(client,session)
        for _ in range(6):
            if not state.get('modal'): break
            request(client,session,'action',name='close_modal'); state=read_state(client,session)
        request(client,session,'new')
        cmds=['SETVAR INSUNITS 6','LINE 0,0 4,0','LINE 4,0 4,1',
              'DIMSTYLE NEW OCS_PRINT_TEST','DIMSTYLE SET OCS_PRINT_TEST dimtxt 0.2',
              'DIMSTYLE SET OCS_PRINT_TEST dimasz 0.08',
              'DIMSTYLE SET OCS_PRINT_TEST dimgap 0.03',
              'DIMSTYLE SET OCS_PRINT_TEST dimscale 1',
              'DIMSTYLE SET OCS_PRINT_TEST dimlfac 1','CDIMSTY OCS_PRINT_TEST',
              'TEXT 0.5,0.5 0.2 0 TEST123','DIMLINEAR 0,0 4,0 2,-0.5']
        if bylayer_weights:
            cmds=['SETVAR INSUNITS 6','LAYER NEW A-THIN','LAYER NEW A-THICK',
                  'CLAYER A-THIN','LINE 0,0 4,0','CLAYER A-THICK',
                  'LINE 4,0 4,1','CLAYER 0',*cmds[3:]]
        report['commands']=cmds
        report['creation']=request(client,session,'run_script',strict=True,commands=cmds)
        if report['creation'].get('completed_commands') != len(cmds):
            raise ProtocolError('Synthetic commands did not complete')
        handles=[c['handle'] for c in report['creation'].get('changes',[])
                 if c.get('kind')=='Added']
        if len(handles)!=4 or len(set(handles))!=4:
            raise ProtocolError('Expected two lines, text, and dimension')
        report['handles']=handles
        if pen_widths:
            for handle, weight in zip(handles[:2], (13, 70)):
                request(client,session,'set_properties',collection='entities',handle=handle,
                        updates=[{'path':'/common/line_weight','value':{'Value':weight}}])
            report['expected_pen_weight_100th_mm']=[13,70]
        if bylayer_weights:
            for name, weight in (('A-THIN',13),('A-THICK',70)):
                request(client,session,'set_properties',collection='layers',name=name,
                        updates=[{'path':'/line_weight','value':{'Value':weight}}])
            report['expected_layer_weights_100th_mm']={'A-THIN':13,'A-THICK':70}
        report['verified_dwg']=save_verified(client,session,out/'metric-content.dwg')
        request(client,session,'open',path=report['verified_dwg']['path'])
        report['reopened_entities']=[client.tool('ocs_read',{'ocs_session_id':session,
            'op':'query','parameters':{'handle':handle,'detail':'full'}})['entities'][0]
            for handle in handles]
        if [entity['type'] for entity in report['reopened_entities']] != \
                ['Line','Line','Text','Dimension']:
            raise ProtocolError('DWG reopen changed synthetic entity types')
        if pen_widths and [entity['properties']['common']['line_weight']
                           for entity in report['reopened_entities'][:2]] != \
                [{'Value':13},{'Value':70}]:
            raise ProtocolError('DWG reopen changed explicit pen weights')
        if bylayer_weights and [entity['properties']['common']['line_weight']
                                for entity in report['reopened_entities'][:2]] != \
                ['ByLayer','ByLayer']:
            raise ProtocolError('DWG reopen changed ByLayer references')
        if bylayer_weights and [entity['layer'] for entity in
                                report['reopened_entities'][:2]] != ['A-THIN','A-THICK']:
            raise ProtocolError('DWG reopen changed line layers')
        if bylayer_weights:
            layers=client.tool('ocs_read',{'ocs_session_id':session,'op':'records',
                'parameters':{'collection':'layers'}})['records']
            report['reopened_layers']={row['name']:row for row in layers
                if row['name'] in ('A-THIN','A-THICK')}
            if [report['reopened_layers'][name]['properties']['line_weight']
                for name in ('A-THIN','A-THICK')] != [{'Value':13},{'Value':70}]:
                raise ProtocolError('DWG reopen changed layer pen weights')
        report['results']={}
        for denominator in (100,50):
            report['results'][str(denominator)]={}
            request(client,session,'set_metric_page_setup',scale_denominator=denominator)
            report['results'][str(denominator)]['page_setup']=client.tool('ocs_read',
                {'ocs_session_id':session,'op':'metric_page_setup'})
            pdf=out/f'metric-content-{denominator}.pdf'
            state=read_state(client,session)
            result=client.tool('ocs_execute',{'ocs_session_id':session,'request':{'op':'metric_plot_pdf','request_id':'plot-'+str(denominator),'document_id':state['document_id'],'revision':state['revision'],'path':str(pdf),'scale_denominator':denominator,'require_page_setup':True}})
            report['results'][str(denominator)]['result']=result
            report['results'][str(denominator)]['sha256']=hashlib.sha256(pdf.read_bytes()).hexdigest().upper()
            if result.get('status')!='completed' or result.get('result',{}).get('sha256')!=\
                    report['results'][str(denominator)]['sha256']:
                raise ProtocolError('Metric PDF operation or digest differs')
            reader=PdfReader(str(pdf))
            if len(reader.pages)!=1:
                raise ProtocolError('Expected one PDF page')
            box=reader.pages[0].mediabox
            page_mm=[float(box.width)*25.4/72,float(box.height)*25.4/72]
            if abs(page_mm[0]-297)>0.2 or abs(page_mm[1]-210)>0.2:
                raise ProtocolError('PDF page differs from A4 landscape')
            report['results'][str(denominator)]['page_mm']=page_mm
            extracted=reader.pages[0].extract_text()
            report['results'][str(denominator)]['extracted_text']=extracted
            if extracted.count('TEST123') != 1:
                raise ProtocolError('Expected one searchable TEST123 CAD TEXT in PDF')
            subprocess.run(['pdftoppm','-f','1','-singlefile','-png','-r','100',str(pdf),str(out/f'metric-content-{denominator}')],check=True)
            components=ink_components(out/f'metric-content-{denominator}.png')
            main=max((s for s in components if s[2]>100 and 30<s[3]<100),
                     key=lambda s:s[2],default=None)
            if main is None:
                raise ProtocolError('Main L linework absent')
            label=[s for s in components if 3<=s[2]<=15 and 8<=s[3]<=22 and
                   main[1]<s[1]<main[1]+main[3]/2 and s[4]>=10]
            dim=[s for s in components if 3<=s[2]<=15 and 6<=s[3]<=22 and
                 main[1]+main[3]<s[1]<main[1]+main[3]+30 and s[4]>=10]
            if len(label)!=7 or len(dim)!=1:
                raise ProtocolError('Text or dimension glyphs absent or overlapping')
            expected_width=4*1000/denominator*100/25.4
            if abs(main[2]-expected_width)>3:
                raise ProtocolError('Linework has wrong physical scale')
            glyph_height=max(s[3] for s in label)
            dim_height=dim[0][3]
            expected_glyph=0.2*1000/denominator*100/25.4
            if not (0.8*expected_glyph <= glyph_height <= 1.3*expected_glyph) or \
                    not (0.7*expected_glyph <= dim_height <= 1.3*expected_glyph):
                raise ProtocolError('Text or dimension glyph has wrong physical scale')
            report['results'][str(denominator)]['raster_100dpi']={
                'main_line_bbox':main[:4],'label_glyph_count':len(label),
                'label_height_px':glyph_height,'dimension_glyph_count':len(dim),
                'dimension_height_px':dim_height}
            if width_qa:
                image=Image.open(out/f'metric-content-{denominator}.png').convert('L')
                sample_x=main[0]+main[2]//3
                sample_y=main[1]+main[3]//3
                horizontal=sum(image.getpixel((sample_x,y))<120
                    for y in range(main[1]+main[3]-8,main[1]+main[3]+2))
                vertical=sum(image.getpixel((x,sample_y))<120
                    for x in range(main[0]+main[2]-8,main[0]+main[2]+2))
                if not (1<=horizontal<=2 and 3<=vertical<=4 and
                        vertical>=horizontal+2):
                    raise ProtocolError('Rendered pen hierarchy differs from DWG weights')
                report['results'][str(denominator)]['raster_100dpi'].update({
                    'thin_horizontal_px':horizontal,'thick_vertical_px':vertical})
        a=report['results']['100']['raster_100dpi']
        b=report['results']['50']['raster_100dpi']
        if abs(b['main_line_bbox'][2]/a['main_line_bbox'][2]-2)>0.05 or \
                abs(b['label_height_px']/a['label_height_px']-2)>0.2:
            raise ProtocolError('Two scales did not preserve physical ratios')
        if width_qa and (a['thin_horizontal_px']!=b['thin_horizontal_px'] or
                           a['thick_vertical_px']!=b['thick_vertical_px']):
            raise ProtocolError('Fixed paper pen widths changed with model scale')
        for _ in range(3):
            if gui.poll() is not None: break
            try:
                request(client,session,'run',cmd='QUIT')
            except (ProtocolError, ToolError, UncertainMutation):
                break
            try: gui.wait(timeout=2)
            except subprocess.TimeoutExpired: pass
    except Exception as exc:
        report['error_type']=type(exc).__name__;report['error']=str(exc)
        raise
    finally:
        client.close()
        if gui.poll() is None:
            gui.terminate()
            try: gui.wait(timeout=5)
            except subprocess.TimeoutExpired: gui.kill();gui.wait(timeout=5)
        report['gui_exited']=gui.poll() is not None
        if report['gui_exited'] and 'error' not in report:
            report['status']='passed'
        (out/'report.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
        print(json.dumps({'path':str(out/'report.json'),'status':report['status'],'error':report.get('error')},indent=2))





if __name__ == "__main__":
    main()
