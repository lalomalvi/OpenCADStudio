# Oráculo reservado M7: congelación previa a L3

`reserved_cohort.py` congela seis imágenes únicas autorizadas en proporción 2 simples, 2 medias y 2 adversariales. `reserved_oracle.py` añade un segundo manifiesto inmutable vinculado al SHA exacto del manifiesto de cohorte. Cada caso requiere un JSON privado con `case_id`, SHA de imagen, declaración de procedencia (`human_verified` o `independent_tool`), referencia de revisión y al menos un criterio explícito en **métrica, topología, semántica y apariencia**. La referencia de revisión es una declaración del preparador; el código no certifica que la persona o herramienta haya revisado correctamente el plano.

El manifiesto público contiene solo IDs, hashes, tamaños y número de criterios. Las imágenes, oráculos íntegros, mapas de rutas y referencias del revisor permanecen fuera de Git. `verify_ready` recalcula hashes de imágenes, oráculos y cohorte antes de cualquier run. Un cambio exige otra cohorte/corte; no se corrige en sitio una congelación observada. `ready_for_L3` significa que la preparación e integridad L0 pasaron, no que un modelo, CAD externo o humano haya aprobado el caso.

Uso local, con mapas JSON privados de ID a ruta absoluta:

```powershell
python docs/automation/masterplan/reserved_oracle.py freeze --cohort <cohort.json> --image-root <imagenes> --image-map <image-map.json> --oracle-root <oraculos> --oracle-map <oracle-map.json> --manifest <oracle-freeze.json>
python docs/automation/masterplan/reserved_oracle.py verify --cohort <cohort.json> --image-root <imagenes> --image-map <image-map.json> --oracle-root <oraculos> --oracle-map <oracle-map.json> --manifest <oracle-freeze.json>
```

Cada oráculo privado tiene este contrato, con criterios reales y verificables para su imagen:

```json
{
  "schema_version": "m7-case-oracle-1",
  "case_id": "case-id",
  "source_sha256": "HASH_SHA256_DE_LA_IMAGEN",
  "verification": {"kind": "human_verified", "reference": "referencia-de-revision"},
  "checks": {
    "metric": [{"id": "m1", "criterion": "medida esperada y tolerancia predefinida"}],
    "topology": [{"id": "t1", "criterion": "relacion de cierre o conectividad"}],
    "semantic": [{"id": "s1", "criterion": "tipo CAD, capa o unidad exigida"}],
    "visual": [{"id": "v1", "criterion": "region y legibilidad exigidas"}]
  }
}
```

Alcance actual: L0 sintético con seis PNG generados y CLI; no se ha congelado ninguna imagen reservada real, no existe oráculo humano del usuario ni evaluación L3/L4/L5 de cohorte. El evaluador futuro debe recibir solo la imagen y contrato de generación, nunca los archivos de oráculo antes de producir su salida.
