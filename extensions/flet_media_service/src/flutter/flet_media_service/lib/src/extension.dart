import 'package:flet/flet.dart';

import 'media_service.dart';

class Extension extends FletExtension {
  @override
  FletService? createService(Control control) {
    switch (control.type) {
      case "MediaService":
        return MediaService(control: control);
      default:
        return null;
    }
  }
}
