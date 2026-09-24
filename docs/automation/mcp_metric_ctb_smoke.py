"""Synthetic L2 proof of a persisted monochrome CTB and colored PDF control."""

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


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def render(pdf, prefix):
    reader = PdfReader(str(pdf))
    if len(reader.pages) != 1:
        raise ProtocolError('Expected one PDF page')
    box = reader.pages[0].mediabox
    page_mm = [float(box.width) * 25.4 / 72, float(box.height) * 25.4 / 72]
    if abs(page_mm[0] - 297) > 0.2 or abs(page_mm[1] - 210) > 0.2:
        raise ProtocolError('PDF page differs from A4 landscape')
    subprocess.run(['pdftoppm', '-f', '1', '-singlefile', '-png', '-r', '100',
                    str(pdf), str(prefix)], check=True, stdout=subprocess.DEVNULL)
    return Image.open(prefix.with_suffix('.png')).convert('RGB'), page_mm


def main():
    repo = Path(__file__).resolve().parents[2]
    server = Path(sys.argv[1] if len(sys.argv) > 1 else repo / 'target/debug/OpenCADStudio.exe').resolve()
    if not server.is_file():
        raise FileNotFoundError(server)
    output = repo / 'target/mcp-isolated' / (time.strftime('%Y%m%d-%H%M%S') +
                                             '-metric-ctb-' + uuid.uuid4().hex[:8])
    output.mkdir(parents=True, exist_ok=False)
    profile, temporary = output / 'profile', output / 'temp'
    profile.mkdir(); temporary.mkdir()
    environment = os.environ.copy()
    environment.update({'APPDATA': str(profile), 'LOCALAPPDATA': str(profile),
                        'TEMP': str(temporary), 'TMP': str(temporary)})
    report = {'schema_version': 'mcp-metric-ctb-l2-1', 'status': 'failed',
              'output': str(output), 'binary_sha256': sha256(server),
              'commands': ['SETVAR INSUNITS 6', 'LINE 0,0 4,0', 'LINE 4,0 4,1']}
    gui = subprocess.Popen([str(server), '--new-instance'], cwd=repo, env=environment,
                           stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL)
    client = Client(server, environment=environment)
    try:
        client.handshake()
        selected = client.ready_session(wait_for_existing=True, timeout=90)
        session = selected['session_id']
        if selected.get('process_id') != gui.pid or \
                Path(selected['executable_path']).resolve() != server:
            raise ProtocolError('Isolated GUI identity differs')
        report['session'] = {'id': session, 'pid': gui.pid}
        state = read_state(client, session)
        for _ in range(6):
            if not state.get('modal'):
                break
            request(client, session, 'action', name='close_modal')
            state = read_state(client, session)
        if state.get('modal'):
            raise ProtocolError('Startup modal remains')
        request(client, session, 'new')
        created = request(client, session, 'run_script', strict=True,
                          commands=report['commands'])
        report['creation'] = created
        if created.get('completed_commands') != 3:
            raise ProtocolError('Synthetic commands did not complete')
        handles = [change['handle'] for change in created.get('changes', [])
                   if change.get('kind') == 'Added']
        if len(handles) != 2:
            raise ProtocolError('Expected two LINE handles')
        report['line_handles'] = handles
        for handle, aci in zip(handles, (1, 3)):
            request(client, session, 'set_properties', collection='entities', handle=handle,
                    updates=[{'path': '/common/color', 'value': {'Index': aci}}])
        request(client, session, 'set_metric_page_setup', scale_denominator=100,
                plot_style='monochrome.ctb')
        report['page_setup_before'] = client.tool('ocs_read', {'ocs_session_id': session,
                                                  'op': 'metric_page_setup'})
        report['verified_dwg'] = save_verified(client, session, output / 'metric-ctb.dwg')
        request(client, session, 'open', path=report['verified_dwg']['path'])
        report['page_setup_after'] = client.tool('ocs_read', {'ocs_session_id': session,
                                                 'op': 'metric_page_setup'})
        if report['page_setup_after'] != report['page_setup_before'] or \
                report['page_setup_after']['plot_style_sheet'] != 'monochrome.ctb' or \
                report['page_setup_after']['plot_plot_styles'] is not True:
            raise ProtocolError('DWG reopen changed monochrome page setup')
        report['line_entities'] = [client.tool('ocs_read', {'ocs_session_id': session,
            'op': 'query', 'parameters': {'handle': handle, 'detail': 'full'}})['entities'][0]
            for handle in handles]
        if [line['properties']['common']['color'] for line in report['line_entities']] != \
                [{'Index': 1}, {'Index': 3}]:
            raise ProtocolError('DWG reopen changed indexed colors')
        for name, style, required in [('color', 'none', False),
                                      ('monochrome', 'monochrome.ctb', True)]:
            state = read_state(client, session)
            pdf = output / f'{name}.pdf'
            result = request(client, session, 'metric_plot_pdf', path=str(pdf),
                             scale_denominator=100, plot_style=style,
                             require_page_setup=required)
            if result.get('status') != 'completed' or \
                    result.get('result', {}).get('sha256') != sha256(pdf):
                raise ProtocolError(f'{name} PDF digest or operation differs')
            image, page_mm = render(pdf, output / name)
            report[name] = {'pdf_sha256': sha256(pdf), 'page_mm': page_mm,
                            'mcp_result': result['result'],
                            'png_sha256': sha256(output / f'{name}.png')}
            if name == 'color':
                colored = image
            else:
                monochrome = image
        red = [(x, y) for y in range(colored.height) for x in range(colored.width)
               if (pixel := colored.getpixel((x, y)))[0] > pixel[1] + 70 and
               pixel[0] > pixel[2] + 70]
        green = [(x, y) for y in range(colored.height) for x in range(colored.width)
                 if (pixel := colored.getpixel((x, y)))[1] > pixel[0] + 70 and
                 pixel[1] > pixel[2] + 70]
        if not red or not green:
            raise ProtocolError('Unstyled PDF does not expose both indexed colors')
        points = red + green
        same_points = [monochrome.getpixel(point) for point in points]
        black = sum(max(pixel) < 80 for pixel in same_points)
        if black / len(same_points) < 0.9:
            raise ProtocolError('Monochrome CTB did not blacken colored linework')
        report['color_oracle'] = {'red_px': len(red), 'green_px': len(green),
                                  'monochrome_black_at_color_px': black,
                                  'sampled_color_px': len(same_points)}
        invalid_path = output / 'invalid-style.pdf'
        try:
            request(client, session, 'metric_plot_pdf', path=str(invalid_path),
                    scale_denominator=100, plot_style='../user.ctb')
        except ToolError as error:
            if 'invalid_plot_style' not in str(error):
                raise
        else:
            raise ProtocolError('An arbitrary CTB name was accepted')
        if invalid_path.exists():
            raise ProtocolError('Rejected CTB wrote a PDF')
        report['arbitrary_style_rejected'] = True
        for _ in range(3):
            if gui.poll() is not None:
                break
            try:
                request(client, session, 'run', cmd='QUIT')
            except (ProtocolError, ToolError, UncertainMutation):
                break
            try:
                gui.wait(timeout=2)
            except subprocess.TimeoutExpired:
                pass
    except Exception as error:
        report['error_type'] = type(error).__name__
        report['error'] = str(error)
        raise
    finally:
        client.close()
        if gui.poll() is None:
            gui.terminate()
            try:
                gui.wait(timeout=5)
            except subprocess.TimeoutExpired:
                gui.kill(); gui.wait(timeout=5)
        report['gui_exited'] = gui.poll() is not None
        if report['gui_exited'] and 'error' not in report:
            report['status'] = 'passed'
        (output / 'report.json').write_text(json.dumps(report, indent=2) + '\n',
                                            encoding='utf-8')
        print(json.dumps({'path': str(output / 'report.json'),
                          'status': report['status'], 'error': report.get('error')}, indent=2))


if __name__ == '__main__':
    main()
