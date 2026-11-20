import 'package:flet/flet.dart';
import 'package:flutter/widgets.dart';

class FletMediaServiceControl extends StatelessWidget {
  final Control control;

  const FletMediaServiceControl({
    super.key,
    required this.control,
  });

  @override
  Widget build(BuildContext context) {
    String text = control.getString("value", "")!;
    Widget myControl = Text(text);

    return LayoutControl(control: control, child: myControl);
  }
}
