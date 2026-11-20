import 'dart:async';

import 'package:audio_service/audio_service.dart';
import 'package:flet/flet.dart';
import 'package:flutter/foundation.dart';
import 'package:just_audio/just_audio.dart';

/// Servicio Flet: reproduce audio con just_audio y expone un MediaSession real
/// (notificación con controles, pantalla de bloqueo, auriculares).
class MediaService extends FletService {
  MediaService({required super.control});

  final AudioPlayer _player = AudioPlayer();
  _ReproductorHandler? _handler;
  StreamSubscription<Duration>? _positionSubscription;
  StreamSubscription<PlayerState>? _stateSubscription;
  int _ultimaPosicion = -1;

  @override
  void init() {
    super.init();
    control.addInvokeMethodListener(_invokeMethod);

    _positionSubscription = _player.positionStream.listen((posicion) {
      final seg = posicion.inSeconds;
      if (seg != _ultimaPosicion) {
        _ultimaPosicion = seg;
        control.triggerEvent("position_change", {"position": seg});
      }
    });

    _stateSubscription = _player.playerStateStream.listen((estado) {
      control.triggerEvent("state_change", {
        "state": estado.playing ? "playing" : "paused",
      });
    });

    _handler = _ReproductorHandler(_player);
    AudioService.init(
      builder: () => _handler!,
      config: const AudioServiceConfig(
        androidNotificationChannelId: 'franzpy.youtube_catalog.audio',
        androidNotificationChannelName: 'Reproducción de video',
        androidNotificationIcon: 'drawable/ic_stat_notify',
        androidStopForegroundOnPause: false,
      ),
    );
  }

  Future<dynamic> _invokeMethod(String name, dynamic args) async {
    switch (name) {
      case "play":
        final url = args["url"] as String;
        await _player.setUrl(url);
        final posicion = int.tryParse(args["position"]?.toString() ?? "0") ?? 0;
        if (posicion > 0) await _player.seek(Duration(seconds: posicion));
        final handler = _handler;
        if (handler != null) {
          final item = MediaItem(
            id: url,
            title: args["titulo"]?.toString() ?? "YouTube Catalog",
            artist: "YouTube",
            artUri: args["caratula"] != null &&
                    args["caratula"].toString().isNotEmpty
                ? Uri.parse(args["caratula"].toString())
                : null,
            duration: Duration(
              seconds: int.tryParse(args["duration"]?.toString() ?? "0") ?? 0,
            ),
          );
          handler.mediaItem.add(item);
          handler.queue.add([item]);
        }
        await _player.play();
        return null;

      case "pause":
        await _player.pause();
        return null;

      case "resume":
        await _player.play();
        return null;

      case "seek":
        final posicion = int.tryParse(args["position"]?.toString() ?? "0") ?? 0;
        await _player.seek(Duration(seconds: posicion));
        return null;

      case "stop":
        await _player.stop();
        return null;

      case "get_position":
        return _player.position.inSeconds;

      default:
        return null;
    }
  }

  @override
  void dispose() {
    _positionSubscription?.cancel();
    _stateSubscription?.cancel();
    _player.dispose();
    super.dispose();
  }
}

class _ReproductorHandler extends BaseAudioHandler with SeekHandler {
  _ReproductorHandler(this._player) {
    _player.playbackEventStream.listen((_) => _difundirEstado());
  }

  final AudioPlayer _player;

  void _difundirEstado() {
    final estado = _player.playerState;
    playbackState.add(
      PlaybackState(
        controls: const [
          MediaControl.skipToPrevious,
          MediaControl.play,
          MediaControl.pause,
          MediaControl.stop,
          MediaControl.skipToNext,
        ],
        systemActions: const {MediaAction.seek},
        androidCompactActionIndices: const [1, 2, 3],
        processingState: const {
          ProcessingState.idle: AudioProcessingState.idle,
          ProcessingState.loading: AudioProcessingState.loading,
          ProcessingState.buffering: AudioProcessingState.buffering,
          ProcessingState.ready: AudioProcessingState.ready,
          ProcessingState.completed: AudioProcessingState.completed,
        }[estado.processingState] ?? AudioProcessingState.idle,
        playing: estado.playing,
        updatePosition: _player.position,
        bufferedPosition: _player.bufferedPosition,
        speed: estado.speed,
      ),
    );
  }

  @override
  Future<void> play() => _player.play();

  @override
  Future<void> pause() => _player.pause();

  @override
  Future<void> seek(Duration position) => _player.seek(position);

  @override
  Future<void> stop() async {
    await _player.stop();
    await super.stop();
  }
}
