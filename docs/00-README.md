# MoiraFlow — Documentación de Arranque

> Paquete de documentación para iniciar el desarrollo de **MoiraFlow**, una
> "Automation Operating System" para SMBs.
> Fecha: 2026-06-24 · Estado: Borrador para arranque · **Todo es tentativo y revisable.**

## Decisiones base (acordadas)

| Dimensión | Decisión |
|-----------|----------|
| Equipo | 1 desarrollador (con asistencia de IA) |
| Motor de ejecución | Sobre **Temporal** (no desde cero) |
| Despliegue inicial | Self-hosted / **Docker** |
| Agentes distribuidos | Incluidos en el MVP, versión "delgada" |

## Índice de documentos

1. **[01 — Factibilidad, Alcance y MVP](01-factibilidad-alcance-mvp.md)**
   Análisis de viabilidad para 1 dev, riesgos, MVP redefinido (vertical fina),
   cambios propuestos sobre el documento original y criterios de aceptación (DoD).

2. **[02 — Arquitectura](02-arquitectura.md)**
   Diagrama lógico, componentes, papel de Temporal, flujos clave, compatibilidad
   con MoiraFlow Architect (IA futura).

3. **[03 — Modelo de Datos](03-modelo-datos.md)**
   Esquema PostgreSQL con `tenant_id` desde el día 1, tablas, estados, auditoría,
   migraciones (Alembic).

4. **[04 — API REST y Esquema de Workflow](04-api-y-esquema-workflow.md)**
   Endpoints de la API (FastAPI) y el formato YAML/JSON del workflow-as-code, con
   reglas de validación.

5. **[05 — Protocolo de Agente y Seguridad](05-protocolo-agente-seguridad.md)**
   Diseño del "agente delgado" como Temporal worker remoto, enrolamiento, mTLS,
   secretos, aislamiento y checklist de seguridad. **Componente de mayor riesgo.**

6. **[06 — Roadmap y ADRs](06-roadmap-y-adr.md)**
   Plan por hitos para 1 dev (~16 semanas al MVP) y registro de decisiones de
   arquitectura.

7. **[07 — Estructura de Repo y Setup Dev](07-repo-y-setup-dev.md)**
   Monorepo, stack, `docker-compose`, variables de entorno, quickstart y primeros
   tickets.

## Cómo leer este paquete

- Si quieres **entender el porqué y el alcance**: empieza por 01 y 06.
- Si vas a **escribir código ya**: 07 → 03 → 04 → 02 → 05.
- Si te interesa **la visión a largo plazo (IA, fases)**: 02 §5 y 06 Parte A.

## Resumen de la postura de diseño

La visión del documento original se mantiene intacta. Lo que cambia es el **orden
de construcción** y dos apuestas que reducen el riesgo a la mitad: **no construir
el motor de ejecución** (usar Temporal) y **reducir el MVP a una vertical fina
end-to-end** en lugar de toda la "Fase 1". Los agentes se incluyen en el MVP pero
en su forma más delgada y con un plan B explícito por ser el mayor riesgo.

## Decisiones cerradas (antes preguntas abiertas)

Resueltas el 2026-06-24 (detalle en [01 §6](01-factibilidad-alcance-mvp.md) y ADRs):

1. **Secretos**: tabla cifrada en Postgres + `secret://` en MVP; Vault dedicado en Fase 2.
2. **Identidad**: JWT propio en MVP; OIDC después.
3. **Sandboxing `command`**: usuario sin privilegios + límites en MVP; contenedor por job en Fase 2.
4. **Idioma**: inglés en producto/UI, i18n-ready (docs internas en español).
5. **Licencia**: open core con núcleo **BSL 1.1** (change date a Apache 2.0); premium comercial.

## Revisión de arquitectura v2 (2026-06-24)

Tras releer el paquete completo, se incorporaron correcciones de fondo (detalle en los ADR-0011
a 0019 de [06](06-roadmap-y-adr.md)). Resumen:

| # | Hallazgo / mejora | Resolución | ADR |
|---|-------------------|-----------|-----|
| 1 | **Determinismo del interpreter**: el replay se corrompe si hay no-determinismo | Orquestación pura en workflow; I/O/secretos/tiempo/templating-con-efectos en activities; **replay tests en CI** | 0011 |
| 2 | **La task queue NO es frontera de seguridad** en Temporal (robo de tareas) | Aislamiento por **cripto** (no por nombre de cola) + namespace por tenant en Fase 3 | 0012 |
| 3 | **Clave de secretos del agente** sin definir | **Par de claves por agente + envelope encryption**; el agente nunca tiene la clave maestra | 0013 |
| 4 | **Contexto mutable** → races en ramas paralelas | Contexto inicial **read-only** + **outputs declarados** por job (sin mutación global) | 0013 |
| 5 | **Idempotencia/doble-escritura** API↔Temporal | `workflow_id` determinista + `executions` como **proyección** (upsert); sin tabla de claves | 0014 |
| + | Cron, payloads, agente, observabilidad, plugins | Temporal Schedules · Data Converter cifrado · **worker local primero** · OTel/Prometheus · plugin = activity+catálogo | 0015–0019 |

> Decisiones de producto que las guiaron (2026-06-24): **producto real a monetizar** (fundaciones
> sólidas) + **arrancar con worker local** y aislar el agente remoto a un hito final con timebox.
