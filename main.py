"""Catálogo de YouTube con reproductor real (flet-video) y reanudación.

La UI corre en el cliente Flet del móvil; Python, SQLite y el proxy del stream
corren en el servidor. El reproductor es media_kit (incluido en el cliente).
"""

from __future__ import annotations

import asyncio
import time
import urllib.request

import flet as ft
import flet_video as ftv

try:
    import flet_notifications as ftn
except ImportError:
    ftn = None

import db
import proxyserver
import youtube

COLORES = [
    "#7E57C2", "#26A69A", "#42A5F5", "#EF5350",
    "#FFA726", "#66BB6A", "#AB47BC", "#78909C",
]
ICONOS = [
    "MUSIC_NOTE", "SCHOOL", "MOVIE", "FAVORITE",
    "SPORTS_SOCCER", "SCIENCE", "PALETTE", "LABEL",
]


def main(page: ft.Page) -> None:
    # En el APK Python corre en el móvil: no hay servidor ni proxy. En `flet run`
    # la app se abre desde una URL http, así que sí usamos el proxy.
    empaquetado = not (page.url or "").startswith("http")
    if not empaquetado:
        proxyserver.start()

    notificaciones = None
    if empaquetado and ftn is not None:
        try:
            notificaciones = ftn.Notifications(android_default_icon="ic_stat_notify")
        except Exception:
            notificaciones = None

    page.title = "YouTube Catalog"
    page.theme_mode = ft.ThemeMode.DARK
    page.theme = ft.Theme(color_scheme_seed=ft.Colors.DEEP_PURPLE)
    page.padding = 0
    page.spacing = 0

    state = {
        "tab": 0,
        "categoria": None,
        "busqueda": "",
        "player_id": None,
        "last_save": 0.0,
        "last_label": 0.0,
        "last_notif": 0.0,
        "media_url": "",
        "headers": {},
        "empaquetado": empaquetado,
    }

    header = ft.Column(spacing=8)
    body = ft.Column(expand=True, scroll=ft.ScrollMode.AUTO, spacing=12)

    nav = ft.NavigationBar(
        destinations=[
            ft.NavigationBarDestination(icon=ft.Icons.VIDEO_LIBRARY, label="Videos"),
            ft.NavigationBarDestination(icon=ft.Icons.CATEGORY, label="Categorías"),
            ft.NavigationBarDestination(icon=ft.Icons.INFO_OUTLINE, label="Info"),
        ],
        selected_index=0,
        on_change=lambda e: on_nav(e),
    )

    status = ft.Text(size=12, color=ft.Colors.ON_SURFACE_VARIANT)
    time_label = ft.Text("0:00 / 0:00", size=13, color=ft.Colors.PRIMARY)
    saved_label = ft.Text("Guardado: 0:00", size=12,
                          color=ft.Colors.ON_SURFACE_VARIANT)
    error_box = ft.Container(
        visible=False,
        padding=12,
        bgcolor=ft.Colors.ERROR_CONTAINER,
        border_radius=12,
        content=ft.Column(
            tight=True,
            spacing=6,
            controls=[
                ft.Text("No se pudo cargar el video", color=ft.Colors.ON_ERROR_CONTAINER),
                error_detail := ft.Text(size=11, color=ft.Colors.ON_ERROR_CONTAINER),
            ],
        ),
    )

    video = ftv.Video(
        expand=True,
        autoplay=True,
        wakelock=False,
        pause_upon_entering_background_mode=False,
        controls=ftv.MaterialVideoControls(
            visible_on_mount=True,
            display_seek_bar=True,
        ),
        on_load=lambda e: page.run_task(on_video_load, e),
        on_position_change=lambda e: on_video_position(e),
        on_complete=lambda e: on_video_complete(e),
        on_error=lambda e: on_video_error(e),
        playlist=[],
    )

    page.on_app_lifecycle_state_change = lambda e: on_lifecycle(e)
    page.add(
        ft.SafeArea(
            expand=True,
            content=ft.Column(controls=[header, body, nav], expand=True, spacing=6),
        )
    )

    # ------------------------------------------------------------------
    # Utilidades
    # ------------------------------------------------------------------
    def snack(mensaje: str) -> None:
        page.show_dialog(ft.SnackBar(ft.Text(mensaje)))

    def icono_nombre(nombre: str):
        return getattr(ft.Icons, nombre, ft.Icons.LABEL)

    def on_nav(e) -> None:
        if state.get("player_id"):
            page.run_task(detener_notificacion)
        state["tab"] = e.control.selected_index
        state["player_id"] = None
        render()

    def on_lifecycle(e) -> None:
        if e.state in (ft.AppLifecycleState.PAUSE, ft.AppLifecycleState.HIDE,
                       ft.AppLifecycleState.INACTIVE):
            page.run_task(save_current)

    # ------------------------------------------------------------------
    # Notificación / foreground service (solo dentro del APK)
    # ------------------------------------------------------------------
    async def iniciar_notificacion(v: db.Video, pos: int) -> None:
        if notificaciones is None:
            return
        try:
            await notificaciones.request_permissions()
            await notificaciones.start_foreground_service(
                1,
                title="YouTube Catalog",
                body=v.titulo[:80],
                service_types=[ftn.AndroidForegroundServiceType.MEDIA_PLAYBACK],
            )
            await actualizar_notificacion(v, pos, forzar=True)
        except Exception:
            pass

    async def actualizar_notificacion(v: db.Video, pos: int, forzar: bool = False) -> None:
        if notificaciones is None:
            return
        ahora = time.monotonic()
        if not forzar and ahora - state["last_notif"] < 5:
            return
        state["last_notif"] = ahora
        opciones = ftn.AndroidOptions(
            progress=ftn.AndroidProgress(value=max(0, int(pos)),
                                         max=max(int(v.duracion or 0), 1)),
            ongoing=True,
            only_alert_once=True,
        )
        try:
            def leer_miniatura():
                with urllib.request.urlopen(v.thumbnail, timeout=8) as resp:
                    return resp.read()

            imagen = await asyncio.to_thread(leer_miniatura)
            opciones = ftn.AndroidOptions(
                style=ftn.AndroidBigPictureStyle(
                    image=ftn.AndroidBytesBitmap(data=imagen),
                    summary_text=v.titulo[:80],
                ),
                progress=opciones.progress,
                ongoing=True,
                only_alert_once=True,
            )
        except Exception:
            pass
        try:
            await notificaciones.show(
                1,
                title=v.titulo[:80],
                body=f"{youtube.fmt_time(pos)} / {youtube.fmt_time(v.duracion)}",
                options=ftn.NotificationOptions(android=opciones),
            )
        except Exception:
            pass

    async def detener_notificacion() -> None:
        if notificaciones is None:
            return
        try:
            await notificaciones.cancel(1)
            await notificaciones.stop_foreground_service()
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Reproductor
    # ------------------------------------------------------------------
    async def save_current() -> None:
        vid = state.get("player_id")
        if not vid:
            return
        try:
            pos = (await video.get_current_position()).in_seconds
            dur = (await video.get_duration()).in_seconds
            completado = 1 if dur and pos >= dur - 2 else 0
            db.save_progress(vid, int(pos), completado)
        except Exception:
            pass

    async def on_video_load(e) -> None:
        vid = state.get("player_id")
        if not vid:
            return
        prog = db.get_progress(vid)
        v = db.get_video(vid)
        dur = v.duracion if v else 0
        pos = prog.posicion_seg if prog and not prog.completado else 0
        if dur and pos >= dur - 1:
            pos = 0
        status.value = "Reproduciendo" + (
            " desde el inicio" if pos == 0 and prog else ""
        )
        if pos > 0:
            try:
                await video.seek(ft.Duration(seconds=pos))
            except Exception:
                pass
        page.update()

    def on_video_position(e) -> None:
        seg = int(e.data.in_seconds)
        ahora = time.monotonic()
        if ahora - state["last_label"] > 0.8:
            state["last_label"] = ahora
            dur = (db.get_video(state["player_id"]).duracion
                   if state.get("player_id") else 0)
            time_label.value = f"{youtube.fmt_time(seg)} / {youtube.fmt_time(dur)}"
            if status.value == "Cargando…":
                status.value = "Reproduciendo"
            page.update()
        if ahora - state["last_save"] >= 5:
            state["last_save"] = ahora
            if state.get("player_id"):
                db.save_progress(state["player_id"], seg, 0)
                v = db.get_video(state["player_id"])
                if v:
                    page.run_task(actualizar_notificacion, v, seg)
            saved_label.value = f"Guardado: {youtube.fmt_time(seg)}"

    def on_video_complete(e) -> None:
        vid = state.get("player_id")
        if vid:
            v = db.get_video(vid)
            db.save_progress(vid, v.duracion if v else 0, 1)
            page.run_task(detener_notificacion)
            snack("Video completado")
            render_player(vid)

    def on_video_error(e) -> None:
        error_detail.value = str(e.data)[:180]
        error_box.visible = True
        status.value = "Error"
        page.update()

    async def volver(e=None) -> None:
        await save_current()
        await detener_notificacion()
        state["player_id"] = None
        state["tab"] = 0
        render()

    def abrir_reproductor(video_id: int) -> None:
        page.run_task(preparar_reproductor, video_id)

    async def preparar_reproductor(video_id: int) -> None:
        v = db.get_video(video_id)
        if not v:
            return
        snack("Cargando video…")
        try:
            # Resolver el stream antes de entregárselo al reproductor: la primera
            # llamada a yt-dlp tarda unos segundos y media_kit tiene timeout corto.
            if empaquetado:
                url, headers = await asyncio.to_thread(
                    youtube.get_stream, v.youtube_id
                )
            else:
                url = proxyserver.stream_url(v.youtube_id)
                headers = {"Referer": "https://www.youtube.com/"}
                await asyncio.to_thread(youtube.get_stream, v.youtube_id)
            state["media_url"] = url
            state["headers"] = headers
        except Exception as ex:
            snack(f"No se pudo cargar: {str(ex)[:90]}")
            return
        state["player_id"] = video_id
        render_player(video_id)
        prog = db.get_progress(video_id)
        await iniciar_notificacion(v, prog.posicion_seg if prog else 0)

    def render_player(video_id: int) -> None:
        v = db.get_video(video_id)
        if not v:
            state["player_id"] = None
            render()
            return
        prog = db.get_progress(v.id)
        guardada = prog.posicion_seg if prog else 0
        state["last_save"] = time.monotonic()
        error_box.visible = False
        status.value = "Cargando…"
        time_label.value = (
            f"{youtube.fmt_time(guardada)} / {youtube.fmt_time(v.duracion)}"
        )
        saved_label.value = f"Guardado: {youtube.fmt_time(guardada)}"
        video.playlist = [
            ftv.VideoMedia(state["media_url"], http_headers=state["headers"])
        ]
        page.floating_action_button = None
        nav.visible = False
        page.appbar = ft.AppBar(
            leading=ft.IconButton(ft.Icons.ARROW_BACK, on_click=volver),
            title=ft.Text(v.titulo, size=15, max_lines=1,
                          overflow=ft.TextOverflow.ELLIPSIS),
            bgcolor=ft.Colors.SURFACE,
        )
        header.controls = []
        body.controls = [
            ft.Container(
                height=230,
                clip_behavior=ft.ClipBehavior.ANTI_ALIAS,
                border_radius=ft.BorderRadius.all(12),
                content=video,
            ),
            error_box,
            ft.Container(
                padding=ft.Padding.symmetric(horizontal=16),
                content=ft.Column(
                    spacing=10,
                    controls=[
                        ft.Row([ft.Icon(ft.Icons.PLAY_CIRCLE_OUTLINE, size=16), status]),
                        ft.Text(v.titulo, size=16, weight=ft.FontWeight.W_600),
                        ft.Row(
                            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                            controls=[
                                time_label,
                                saved_label,
                            ],
                        ),
                        ft.Row(
                            wrap=True,
                            alignment=ft.MainAxisAlignment.CENTER,
                            controls=[
                                ft.FilledTonalButton(
                                    "Guardar aquí",
                                    icon=ft.Icons.SAVE,
                                    on_click=guardar_posicion,
                                ),
                                ft.OutlinedButton(
                                    "Completado",
                                    icon=ft.Icons.CHECK,
                                    on_click=lambda e: marcar_completado(v.id),
                                ),
                            ],
                        ),
                        ft.Button(
                            "Abrir en YouTube (segundo plano / PiP)",
                            icon=ft.Icons.LAUNCH,
                            width=float("inf"),
                            action=ft.OpenUrl(
                                youtube.watch_url(v.youtube_id, guardada)
                            ),
                        ),
                        ft.Text(
                            "El audio sigue al cambiar de app (mejor esfuerzo). "
                            "Con pantalla apagada usa el botón de YouTube.",
                            size=11,
                            color=ft.Colors.OUTLINE,
                        ),
                    ],
                ),
            ),
        ]
        page.update()

    async def guardar_posicion(e) -> None:
        vid = state.get("player_id")
        if not vid:
            return
        try:
            pos = int((await video.get_current_position()).in_seconds)
            db.save_progress(vid, pos, 0)
            snack(f"Guardado en {youtube.fmt_time(pos)}")
        except Exception:
            snack("No se pudo guardar")
        page.update()

    def marcar_completado(video_id: int) -> None:
        v = db.get_video(video_id)
        db.save_progress(video_id, v.duracion if v else 0, 1)
        snack("Marcado como completado")
        render_player(video_id)

    # ------------------------------------------------------------------
    # Catálogo
    # ------------------------------------------------------------------
    def build_catalog_header() -> None:
        chips = [
            ft.Chip(
                label=ft.Text("Todos"),
                selected=state["categoria"] is None,
                on_click=lambda e: seleccionar_categoria(None),
            )
        ]
        for c in db.list_categories():
            chips.append(
                ft.Chip(
                    label=ft.Text(c.nombre),
                    selected=state["categoria"] == c.id,
                    on_click=lambda e, cid=c.id: seleccionar_categoria(cid),
                )
            )
        header.controls = [
            ft.Text("Mi catálogo", size=22, weight=ft.FontWeight.BOLD),
            ft.Row(controls=chips, scroll=ft.ScrollMode.AUTO),
            ft.TextField(
                value=state["busqueda"],
                hint_text="Buscar videos…",
                prefix_icon=ft.Icons.SEARCH,
                on_change=on_search,
                filled=True,
            ),
        ]

    def seleccionar_categoria(cid: int | None) -> None:
        state["categoria"] = cid
        render()

    def on_search(e) -> None:
        state["busqueda"] = e.control.value or ""
        render_catalog_list()

    def tarjeta_video(v: db.Video) -> ft.Control:
        prog = db.get_progress(v.id)
        pos = prog.posicion_seg if prog else 0
        dur = v.duracion or 0
        ratio = min(1.0, pos / dur) if dur else (1.0 if prog and prog.completado else 0.0)
        cat = next((c for c in db.list_categories() if c.id == v.categoria_id), None)
        miniatura = (
            v.thumbnail or f"https://i.ytimg.com/vi/{v.youtube_id}/hqdefault.jpg"
        )
        return ft.Card(
            elevation=1,
            content=ft.Container(
                padding=0,
                clip_behavior=ft.ClipBehavior.ANTI_ALIAS,
                border_radius=ft.BorderRadius.all(14),
                content=ft.Column(
                    spacing=0,
                    tight=True,
                    controls=[
                        ft.GestureDetector(
                            on_tap=lambda e, vid=v.id: abrir_reproductor(vid),
                            content=ft.Stack(
                                controls=[
                                    ft.Image(
                                        src=miniatura,
                                        width=float("inf"),
                                        height=190,
                                        fit=ft.BoxFit.COVER,
                                        error_content=ft.Container(
                                            height=190,
                                            bgcolor=ft.Colors.SURFACE_CONTAINER_HIGHEST,
                                            alignment=ft.Alignment.CENTER,
                                            content=ft.Icon(ft.Icons.MUSIC_NOTE, size=40),
                                        ),
                                    ),
                                    ft.Container(
                                        alignment=ft.Alignment.BOTTOM_RIGHT,
                                        padding=8,
                                        content=ft.Container(
                                            padding=ft.Padding.symmetric(horizontal=8, vertical=4),
                                            border_radius=8,
                                            bgcolor=ft.Colors.BLACK_54,
                                            content=ft.Text(
                                                youtube.fmt_time(dur) if dur else "--:--",
                                                size=11,
                                            ),
                                        ),
                                    ),
                                ],
                            ),
                        ),
                        ft.Container(
                            padding=ft.Padding.all(12),
                            content=ft.Column(
                                spacing=8,
                                tight=True,
                                controls=[
                                    ft.Text(
                                        v.titulo,
                                        size=15,
                                        weight=ft.FontWeight.W_600,
                                        max_lines=2,
                                        overflow=ft.TextOverflow.ELLIPSIS,
                                    ),
                                    ft.Row(
                                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                                        controls=[
                                            ft.Row(
                                                spacing=4,
                                                controls=[
                                                    ft.Icon(
                                                        icono_nombre(cat.icono) if cat
                                                        else ft.Icons.LABEL,
                                                        size=14,
                                                        color=cat.color if cat
                                                        else ft.Colors.OUTLINE,
                                                    ),
                                                    ft.Text(
                                                        cat.nombre if cat else "Sin categoría",
                                                        size=12,
                                                        color=ft.Colors.ON_SURFACE_VARIANT,
                                                    ),
                                                ],
                                            ),
                                            ft.Text(
                                                f"{youtube.fmt_time(pos)} / {youtube.fmt_time(dur)}",
                                                size=11,
                                                color=ft.Colors.ON_SURFACE_VARIANT,
                                            ),
                                        ],
                                    ),
                                    ft.ProgressBar(value=ratio, bar_height=5),
                                    ft.Row(
                                        alignment=ft.MainAxisAlignment.END,
                                        controls=[
                                            ft.IconButton(
                                                ft.Icons.EDIT_OUTLINED,
                                                tooltip="Editar",
                                                on_click=lambda e, vv=v: open_video_dialog(vv),
                                            ),
                                            ft.IconButton(
                                                ft.Icons.DELETE_OUTLINE,
                                                tooltip="Borrar",
                                                on_click=lambda e, vv=v: confirmar_borrado_video(vv),
                                            ),
                                            ft.FilledButton(
                                                "Reproducir",
                                                icon=ft.Icons.PLAY_ARROW,
                                                on_click=lambda e, vid=v.id: abrir_reproductor(vid),
                                            ),
                                        ],
                                    ),
                                ],
                            ),
                        ),
                    ],
                ),
            ),
        )

    def render_catalog_list() -> None:
        videos = db.list_videos(state["categoria"], state["busqueda"])
        if videos:
            body.controls = [tarjeta_video(v) for v in videos]
        else:
            body.controls = [
                ft.Container(
                    padding=ft.Padding.symmetric(vertical=60),
                    alignment=ft.Alignment.CENTER,
                    content=ft.Column(
                        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                        spacing=8,
                        controls=[
                            ft.Icon(ft.Icons.VIDEO_LIBRARY, size=52,
                                    color=ft.Colors.OUTLINE),
                            ft.Text("No hay videos aquí", size=17),
                            ft.Text("Pulsa + para añadir un link de YouTube", size=13),
                        ],
                    ),
                )
            ]
        page.update()

    # ------------------------------------------------------------------
    # Categorías e info
    # ------------------------------------------------------------------
    def render_categories() -> None:
        header.controls = [
            ft.Text("Categorías", size=22, weight=ft.FontWeight.BOLD),
            ft.Text("Organiza tus videos", size=13,
                    color=ft.Colors.ON_SURFACE_VARIANT),
        ]
        rows = []
        for c in db.list_categories():
            n = len(db.list_videos(c.id))
            rows.append(
                ft.Card(
                    content=ft.ListTile(
                        leading=ft.CircleAvatar(
                            bgcolor=c.color,
                            content=ft.Icon(icono_nombre(c.icono),
                                            color=ft.Colors.WHITE),
                        ),
                        title=ft.Text(c.nombre),
                        subtitle=ft.Text(f"{n} video(s)"),
                        trailing=ft.Row(
                            spacing=0,
                            controls=[
                                ft.IconButton(
                                    ft.Icons.EDIT_OUTLINED,
                                    on_click=lambda e, cc=c: open_category_dialog(cc),
                                ),
                                ft.IconButton(
                                    ft.Icons.DELETE_OUTLINE,
                                    on_click=lambda e, cc=c: confirmar_borrado_categoria(cc),
                                ),
                            ],
                        ),
                    )
                )
            )
        body.controls = rows or [ft.Text("Todavía no hay categorías.")]
        page.update()

    def render_info() -> None:
        header.controls = [ft.Text("Información", size=22, weight=ft.FontWeight.BOLD)]
        body.controls = [
            ft.Card(
                content=ft.Container(
                    padding=18,
                    content=ft.Column(
                        spacing=12,
                        controls=[
                            ft.Text(
                                "Reproductor real dentro de la app. Al abrir un video "
                                "arranca desde la posición guardada y la va guardando "
                                "cada pocos segundos.",
                                size=14,
                            ),
                            ft.Text(
                                "El audio continúa al cambiar de app (mejor esfuerzo). "
                                "Con la pantalla apagada, Android puede detenerlo porque "
                                "el cliente Flet no tiene servicio en segundo plano: usa "
                                "el botón «Abrir en YouTube» para ese caso.",
                                size=13,
                                color=ft.Colors.ON_SURFACE_VARIANT,
                            ),
                            ft.Text(
                                "Necesitas que el servidor Python siga en marcha.",
                                size=12,
                                color=ft.Colors.OUTLINE,
                            ),
                        ],
                    ),
                )
            )
        ]
        page.update()

    # ------------------------------------------------------------------
    # Render general
    # ------------------------------------------------------------------
    def render() -> None:
        nav.visible = True
        nav.selected_index = state["tab"]
        page.floating_action_button = None
        if state["tab"] == 0:
            page.appbar = ft.AppBar(
                title=ft.Text("YouTube Catalog", weight=ft.FontWeight.BOLD),
                bgcolor=ft.Colors.SURFACE,
                actions=[
                    ft.IconButton(
                        ft.Icons.ADD,
                        tooltip="Añadir video",
                        on_click=lambda e: open_video_dialog(),
                    )
                ],
            )
            build_catalog_header()
            render_catalog_list()
        elif state["tab"] == 1:
            page.appbar = ft.AppBar(
                title=ft.Text("YouTube Catalog", weight=ft.FontWeight.BOLD),
                bgcolor=ft.Colors.SURFACE,
                actions=[
                    ft.IconButton(
                        ft.Icons.ADD,
                        tooltip="Nueva categoría",
                        on_click=lambda e: open_category_dialog(),
                    )
                ],
            )
            render_categories()
        else:
            page.appbar = ft.AppBar(
                title=ft.Text("YouTube Catalog", weight=ft.FontWeight.BOLD),
                bgcolor=ft.Colors.SURFACE,
            )
            render_info()
        page.update()

    # ------------------------------------------------------------------
    # Diálogos (bottom sheets)
    # ------------------------------------------------------------------
    def confirmar_borrado_video(v: db.Video) -> None:
        def borrar(e) -> None:
            page.pop_dialog()
            db.delete_video(v.id)
            snack("Video eliminado")
            render()

        page.show_dialog(
            ft.AlertDialog(
                modal=True,
                title=ft.Text("¿Borrar video?"),
                content=ft.Text(v.titulo, max_lines=3),
                actions=[
                    ft.TextButton("Cancelar", on_click=lambda e: page.pop_dialog()),
                    ft.TextButton("Borrar", on_click=borrar),
                ],
            )
        )

    def confirmar_borrado_categoria(c: db.Category) -> None:
        def borrar(e) -> None:
            page.pop_dialog()
            db.delete_category(c.id)
            if state["categoria"] == c.id:
                state["categoria"] = None
            snack("Categoría eliminada")
            render()

        page.show_dialog(
            ft.AlertDialog(
                modal=True,
                title=ft.Text("¿Borrar categoría?"),
                content=ft.Text("Los videos quedarán sin categoría."),
                actions=[
                    ft.TextButton("Cancelar", on_click=lambda e: page.pop_dialog()),
                    ft.TextButton("Borrar", on_click=borrar),
                ],
            )
        )

    def open_video_dialog(v: db.Video | None = None) -> None:
        cats = db.list_categories()
        url_field = ft.TextField(
            label="Link de YouTube",
            value=youtube.canonical_url(v.youtube_id) if v else "",
            hint_text="https://www.youtube.com/watch?v=…",
            autofocus=v is None,
            filled=True,
        )
        titulo_field = ft.TextField(
            label="Título",
            value=v.titulo if v else "",
            filled=True,
        )
        dur_field = ft.TextField(
            label="Duración (segundos)",
            value=str(v.duracion) if v and v.duracion else "",
            keyboard_type=ft.KeyboardType.NUMBER,
            filled=True,
        )
        cat_drop = ft.Dropdown(
            label="Categoría",
            value=str(v.categoria_id) if v and v.categoria_id else "",
            options=[
                ft.DropdownOption(key="", text="Sin categoría"),
                *[ft.DropdownOption(key=str(c.id), text=c.nombre) for c in cats],
            ],
        )

        async def buscar(e) -> None:
            vid = youtube.extract_video_id(url_field.value or "")
            if not vid:
                snack("Pega un link válido")
                return
            meta = await asyncio.to_thread(youtube.fetch_metadata, url_field.value, vid)
            titulo_field.value = meta["titulo"]
            dur_field.value = str(meta["duracion"]) if meta["duracion"] else ""
            page.update()
            snack("Datos cargados")

        def guardar(e) -> None:
            vid = youtube.extract_video_id(url_field.value or "")
            if not vid:
                snack("Pega un link válido de YouTube")
                return
            titulo = (titulo_field.value or "").strip() or vid
            try:
                duracion = int(dur_field.value or 0)
            except ValueError:
                duracion = 0
            try:
                cat_id = int(cat_drop.value) if cat_drop.value else None
            except ValueError:
                cat_id = None
            if v:
                db.update_video(v.id, titulo, duracion, cat_id)
                snack("Video actualizado")
            else:
                meta = youtube.fetch_metadata(url_field.value, vid)
                db.add_video(
                    vid,
                    youtube.canonical_url(vid),
                    titulo if titulo_field.value else meta["titulo"],
                    meta["thumbnail"],
                    duracion or meta["duracion"],
                    cat_id,
                )
                snack("Video añadido")
            page.pop_dialog()
            render()

        sheet = ft.BottomSheet(
            scrollable=True,
            show_drag_handle=True,
            use_safe_area=True,
            content=ft.Container(
                padding=ft.Padding.only(left=20, right=20, bottom=24),
                content=ft.Column(
                    tight=True,
                    spacing=10,
                    controls=[
                        ft.Text("Editar video" if v else "Añadir video",
                                size=19, weight=ft.FontWeight.BOLD),
                        url_field,
                        ft.OutlinedButton(
                            "Buscar título y duración",
                            icon=ft.Icons.SEARCH,
                            on_click=buscar,
                        ),
                        titulo_field,
                        dur_field,
                        cat_drop,
                        ft.Row(
                            alignment=ft.MainAxisAlignment.END,
                            controls=[
                                ft.TextButton("Cancelar",
                                              on_click=lambda e: page.pop_dialog()),
                                ft.FilledButton("Guardar", on_click=guardar),
                            ],
                        ),
                    ],
                ),
            ),
        )
        page.show_dialog(sheet)

    def open_category_dialog(c: db.Category | None = None) -> None:
        nombre = ft.TextField(
            label="Nombre", value=c.nombre if c else "", filled=True
        )
        color_sel = {"valor": c.color if c else COLORES[0]}
        icono_sel = {"valor": c.icono if c else ICONOS[0]}
        color_chips: list[ft.Chip] = []
        icon_chips: list[ft.Chip] = []

        def elegir_color(color: str) -> None:
            color_sel["valor"] = color
            for chip in color_chips:
                chip.selected = chip.data == color
            page.update()

        def elegir_icono(nombre_icono: str) -> None:
            icono_sel["valor"] = nombre_icono
            for chip in icon_chips:
                chip.selected = chip.data == nombre_icono
            page.update()

        for color in COLORES:
            color_chips.append(
                ft.Chip(
                    label=ft.Text("   "),
                    selected=color_sel["valor"] == color,
                    selected_color=color,
                    bgcolor=color,
                    data=color,
                    on_click=lambda e, col=color: elegir_color(col),
                )
            )
        for nombre_icono in ICONOS:
            icon_chips.append(
                ft.Chip(
                    label=ft.Icon(icono_nombre(nombre_icono), size=18),
                    selected=icono_sel["valor"] == nombre_icono,
                    data=nombre_icono,
                    on_click=lambda e, ic=nombre_icono: elegir_icono(ic),
                )
            )

        def guardar(e) -> None:
            if not (nombre.value or "").strip():
                snack("Escribe un nombre")
                return
            if c:
                db.update_category(c.id, nombre.value, color_sel["valor"],
                                   icono_sel["valor"])
                snack("Categoría actualizada")
            else:
                db.add_category(nombre.value, color_sel["valor"], icono_sel["valor"])
                snack("Categoría creada")
            page.pop_dialog()
            render()

        page.show_dialog(
            ft.BottomSheet(
                scrollable=True,
                show_drag_handle=True,
                use_safe_area=True,
                content=ft.Container(
                    padding=ft.Padding.only(left=20, right=20, bottom=24),
                    content=ft.Column(
                        tight=True,
                        spacing=10,
                        controls=[
                            ft.Text("Editar categoría" if c else "Nueva categoría",
                                    size=19, weight=ft.FontWeight.BOLD),
                            nombre,
                            ft.Text("Color", size=12),
                            ft.Row(wrap=True, controls=color_chips),
                            ft.Text("Icono", size=12),
                            ft.Row(wrap=True, controls=icon_chips),
                            ft.Row(
                                alignment=ft.MainAxisAlignment.END,
                                controls=[
                                    ft.TextButton("Cancelar",
                                                  on_click=lambda e: page.pop_dialog()),
                                    ft.FilledButton("Guardar", on_click=guardar),
                                ],
                            ),
                        ],
                    ),
                ),
            )
        )

    render()


if __name__ == "__main__":
    ft.run(main)
