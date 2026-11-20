# YouTube Catalog (Flet, Android)

Catálogo de videos de YouTube con categorías, búsqueda y guardado de la posición
de reproducción.

## Arquitectura

La interfaz corre en el **cliente Flet** del teléfono; Python y SQLite corren en
el servidor de esta máquina. No se compila APK.

- El catálogo, las categorías y el progreso se guardan en `data/catalog.db`.
- `youtube.py` obtiene título, miniatura y duración con `yt-dlp` (respaldo: oEmbed).
- Al reproducir se abre YouTube con `&t=<segundos>s`, para arrancar donde se dejó.
- El audio en segundo plano y el PiP los hace la app de YouTube/VLC del móvil.
- `session.py` estima la posición mientras el video está fuera de la app; al volver
  se puede corregir con el slider y pulsar **Guardar posición**.

## Ejecutar en el teléfono

```bash
python3 ~/.config/opencode/skills/flet-android/scripts/flet_android.py \
  --project "/root/trabajos flet/youtube-catalog"
```

Tras cambiar código, añadir `--restart`. Para detener el servidor, `--stop`.

## Limitaciones conocidas

- El cliente Flet no puede reproducir audio en segundo plano por sí mismo; la
  reproducción se delega a YouTube/VLC.
- No se puede leer la posición exacta del reproductor externo; se estima con un
  temporizador y se corrige manualmente.
- YouTube cambia sus formatos con frecuencia: mantener `yt-dlp` actualizado.
- La app requiere que el servidor Python siga en marcha y el móvil conectado.
# Build-flet
