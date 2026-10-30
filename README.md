# SAAD-Campus — Evaluación 2, Arquitectura de Software
**Integrantes:** Fabián Medel · Mahicol Valenzuela

## 📌 Entrega
| | |
|---|---|
| 📄🎥 **Informe y video** | **[Abrir carpeta en Google Drive](https://drive.google.com/drive/folders/1r_dy1ly3OYZxK2j1vGHH0ZGnDLx1DnTS?usp=sharing)** |
| 🛠️ **Cómo ejecutarlo** | [INSTALACION.md](INSTALACION.md) |

## Arquitectura
| Equipo | Carpeta | Componentes |
|---|---|---|
| Servidor central | [`central/`](central/) | Panel Flutter, API FastAPI, PostgreSQL (Docker), auditoría, WebSocket, proxy mTLS |
| Nodo edge | [`edge/`](edge/) | Kiosco web, YuNet + SFace (OpenCV), SQLCipher, sincronización offline |

La decisión de acceso se toma **localmente en el edge**. La central administra permisos y recibe los eventos por HTTPS con certificado de cliente (mTLS).

> Por seguridad, el repositorio no incluye credenciales (`.env`, certificados ni base cifrada); se generan en cada instalación siguiendo [INSTALACION.md](INSTALACION.md).
