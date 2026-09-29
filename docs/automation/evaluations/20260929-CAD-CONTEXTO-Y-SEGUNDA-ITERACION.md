# Evaluación CAD conversacional: creación y segunda iteración (2026-09-29)

Este documento registra un ensayo local del asistente y el MCP, sin modificar el servidor. No implica publicación de dibujos, aceptación M7 ni compatibilidad externa. Las imágenes, DWG, contexto detallado y transcripciones privadas quedan bajo target/mcp-isolated, fuera del versionado.

## Resultado y límites

Creación: muros con espesor, vanos, hatches, bloques originales repetidos, cotas métricas, rótulos y cuadro de áreas. Edición: copia nativa del DWG propio, cambios selectivos en recintos existentes y una ampliación, save_verified y reapertura explícita. La segunda iteración conserva 184 entidades con geometría/capa iguales y transforma otras cinco de las existentes.

Consulta de referencias de bloques: bounds pueden quedar degenerados en la inserción, y una búsqueda por ventana interior al símbolo devuelve cero. No usar esa vía como prueba de colisión. block_define crea la primera referencia en capa 0; verificar y normalizar explícitamente capa de referencia/contenido. Ambas limitaciones permanecen pendientes de corrección en el producto.

## Contrato para modificaciones

1. Identificar el dibujo propio: ruta absoluta, SHA256, unidades, propietario de sesión, documento y revisión. Consultar estado actual y detener dependencias ante incertidumbre.
2. Crear una nueva copia nativa con new/template; conservar el archivo anterior. Releer handles y tipos de la copia.
3. Resolver el pedido en roles y criterios observables. Aclarar el alcance que cambie el sitio; no inventar superficie disponible.
4. Generar un plan congelado de selectors y handles. Exigir cardinalidad esperada y pertenencia a Model; no seleccionar definiciones ni otros documentos.
5. Seleccionar textos por contenido y posición, no solo por contenido. Seleccionar bloques por identidad y transformaciones comprobadas; no asumir bounds correctos.
6. Preferir transformar referencias existentes a redibujar geometría. Para muros/vanos, modificar solo segmentos afectados y sus hatches. Validar también la coherencia de rótulos y cotas.
7. Ejecutar por MCP en lotes strict acotados. Conservar request_id, respuestas, índices completos y toda corrección. Timeout/respuesta perdida: consultar la operación original, nunca repetir ciegamente.
8. Comprobar invariantes del contexto anterior fuera del cambio, geometría modificada y nuevos objetos. Comparar tipos/capas/posiciones/radios y medidas relevantes; separar revisión visual de comprobación automática completa.
9. Auditar, save_verified, abrir el nuevo archivo, consultar y capturar el documento reabierto. Rehashar original y entrega. Persistencia interna no equivale a interoperabilidad independiente.
10. Guardar contexto recuperable y registro de consumo/tiempo con corte y denominador explícitos. No reemplazar futuras lecturas de autoridad por un contexto viejo.

## Contexto recuperable

El esquema local owned-cad-context-1 guarda ruta/hash, unidades, programa de recintos, estado de sesión/documento/revisión, geometría de cada handle y fingerprint, definiciones propias de símbolos y enlaces de historia. Su uso debe verificar primero que el DWG y los registros actuales concuerdan; puede quedar obsoleto tras una edición manual o un nuevo guardado. No mezclar memoria del agente, registro semántico y verdad del CAD.

## Incidentes del adaptador, no del servidor

- Lectura summary no disponible: rechazo explícito; continuar desde la lectura correcta sin repetir geometría.
- En Windows, dos nombres que solo difieren por mayúsculas colisionan. Separar nombres de instrucciones y metadatos.
- Textos repetidos entre recintos/cuadro: elegir solo por contenido editó el elemento incorrecto; usar contenido + posición/rol con coincidencia única.
- TEXT normaliza espacios: validar contenido normalizado cuando corresponda, manteniendo posición e identidad como restricciones.

## Medición y optimización

Usar deltas de token_count del hilo para entrada, cache y salida; razonamiento es subconjunto de salida. El contexto reenviado suma entrada en cada respuesta y cache es subconjunto de entrada. No inferir costo facturado ni confundir tokens con tamaño del archivo.

Separar tiempo total de conversación, suma de RPC a herramientas, tiempo de mutaciones del cliente y tiempo de backend. Conservar el corte de V2, porque se recoge antes de la respuesta final. Creación y edición son cargas diferentes, no una prueba controlada de mejora.

Prioridades sugeridas: patches semánticos breves, registro de contexto compacto, cliente persistente, transformaciones agrupadas y consultas proyectadas por handles. Mantener lectura de identidad, comprobación de invariantes, auditoría y reapertura. Corregir límites de INSERT antes de aceptar QA espacial de muebles. Los datos y tablas concretas permanecen en los informes locales del ensayo.

## Consolidación posterior

[Informe maestro, métricas y backlog R01-R19](../masterplan/06-INFORME-MAESTRO-Y-MEJORAS-20260929.md). Conserva cortes, denominadores y límites de estas iteraciones; los agregados sanitizados e índice de hashes están versionados allí y los dibujos/logs continúan privados.
