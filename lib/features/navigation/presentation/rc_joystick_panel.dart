import 'dart:async';
import 'dart:math' as math;
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../../../core/theme/app_theme.dart';
import '../../../services/hardware_communication_service.dart';
import '../application/navigation_providers.dart';

class AnalogJoystickPanel extends ConsumerStatefulWidget {
  const AnalogJoystickPanel({super.key});

  @override
  ConsumerState<AnalogJoystickPanel> createState() => _AnalogJoystickPanelState();
}

class _AnalogJoystickPanelState extends ConsumerState<AnalogJoystickPanel> {
  Offset _dragOffset = Offset.zero;
  final double _joystickRadius = 100.0;
  final double _knobRadius = 30.0;
  String _currentCommand = 'RC_S';
  Timer? _commandTimer;

  // To prevent spamming Bluetooth, we'll only send command occasionally if holding
  // But for simple RC, we only send when command string CHANGES.
  
  @override
  void dispose() {
    _commandTimer?.cancel();
    super.dispose();
  }

  void _updateJoystick(Offset newPos) {
    setState(() {
      _dragOffset = newPos;
    });

    // Analog normalized values (-100 to 100)
    final double x = (_dragOffset.dx / _joystickRadius) * 100;
    final double y = -(_dragOffset.dy / _joystickRadius) * 100; // Invert Y for Flutter coordinates

    // Deadzone check
    if (_dragOffset.distance < 15.0) {
      _sendCommand("RC:0:0");
    } else {
      // Send as "RC:X:Y" for smooth analog control
      _sendCommand("RC:${x.round()}:${y.round()}");
    }
  }

  void _sendCommand(String cmd) {
    if (_currentCommand != cmd) {
      _currentCommand = cmd;
      ref.read(hardwareServiceProvider).sendRcCommand(cmd);
      debugPrint("Sending RC Command: $cmd");
    }
  }

  void _onPanStart(DragStartDetails details) {
    _updatePosition(details.localPosition);
  }

  void _onPanUpdate(DragUpdateDetails details) {
    _updatePosition(details.localPosition);
  }

  void _onPanEnd(DragEndDetails details) {
    _updateJoystick(Offset.zero); // Reset to center
  }

  void _updatePosition(Offset localPos) {
    // Center is (radius, radius)
    Offset center = Offset(_joystickRadius, _joystickRadius);
    Offset offsetFromCenter = localPos - center;

    // Clamp distance to joystick radius
    if (offsetFromCenter.distance > _joystickRadius) {
      offsetFromCenter = Offset.fromDirection(
        offsetFromCenter.direction,
        _joystickRadius,
      );
    }

    _updateJoystick(offsetFromCenter);
  }

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(vertical: 32),
      decoration: const BoxDecoration(
        color: Color(0xFF121212),
        borderRadius: BorderRadius.only(
          topLeft: Radius.circular(32),
          topRight: Radius.circular(32),
        ),
      ),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          Container(
            width: 48,
            height: 6,
            decoration: BoxDecoration(
              color: Colors.white24,
              borderRadius: BorderRadius.circular(3),
            ),
          ),
          const SizedBox(height: 24),
          const Text(
            'MANUAL DRIVE',
            style: TextStyle(
              color: Colors.white,
              fontSize: 20,
              fontWeight: FontWeight.w800,
              letterSpacing: 2,
            ),
          ),
          const Text(
            'Keep your eyes on the vehicle.',
            style: TextStyle(
              color: Colors.white54,
              fontSize: 12,
            ),
          ),
          const SizedBox(height: 48),
          
          // Joystick Area
          SizedBox(
            width: _joystickRadius * 2,
            height: _joystickRadius * 2,
            child: GestureDetector(
              onPanStart: _onPanStart,
              onPanUpdate: _onPanUpdate,
              onPanEnd: _onPanEnd,
              child: Stack(
                alignment: Alignment.center,
                children: [
                  // Base Circle
                  Container(
                    width: _joystickRadius * 2,
                    height: _joystickRadius * 2,
                    decoration: BoxDecoration(
                      shape: BoxShape.circle,
                      color: Colors.white.withValues(alpha: 0.05),
                      border: Border.all(
                        color: Colors.white.withValues(alpha: 0.1),
                        width: 2,
                      ),
                      boxShadow: [
                        BoxShadow(
                          color: AppColors.primary.withValues(alpha: 0.2),
                          blurRadius: 30,
                          spreadRadius: -10,
                        )
                      ],
                    ),
                    // Directional hints
                    child: const Stack(
                      children: [
                        Align(alignment: Alignment.topCenter, child: Padding(padding: EdgeInsets.all(8.0), child: Icon(Icons.keyboard_arrow_up, color: Colors.white38))),
                        Align(alignment: Alignment.bottomCenter, child: Padding(padding: EdgeInsets.all(8.0), child: Icon(Icons.keyboard_arrow_down, color: Colors.white38))),
                        Align(alignment: Alignment.centerLeft, child: Padding(padding: EdgeInsets.all(8.0), child: Icon(Icons.keyboard_arrow_left, color: Colors.white38))),
                        Align(alignment: Alignment.centerRight, child: Padding(padding: EdgeInsets.all(8.0), child: Icon(Icons.keyboard_arrow_right, color: Colors.white38))),
                      ],
                    ),
                  ),
                  
                  // Moving Knob
                  Transform.translate(
                    offset: _dragOffset,
                    child: Container(
                      width: _knobRadius * 2,
                      height: _knobRadius * 2,
                      decoration: BoxDecoration(
                        color: AppColors.primary,
                        shape: BoxShape.circle,
                        boxShadow: [
                          BoxShadow(
                            color: AppColors.primary.withValues(alpha: 0.5),
                            blurRadius: 15,
                            offset: const Offset(0, 5),
                          )
                        ],
                      ),
                    ),
                  ),
                ],
              ),
            ),
          ),
          
          const SizedBox(height: 48),
          
          // Panic Stop Button
          GestureDetector(
            onTap: () {
              ref.read(hardwareServiceProvider).sendEmergencyStop();
              Navigator.pop(context); // Close the sheet
            },
            child: Container(
              padding: const EdgeInsets.symmetric(horizontal: 32, vertical: 16),
              decoration: BoxDecoration(
                color: Colors.red.withValues(alpha: 0.15),
                borderRadius: BorderRadius.circular(20),
                border: Border.all(color: Colors.red.withValues(alpha: 0.5)),
              ),
              child: const Text(
                'EMERGENCY STOP',
                style: TextStyle(
                  color: Colors.red,
                  fontWeight: FontWeight.bold,
                  letterSpacing: 1.5,
                ),
              ),
            ),
          ),
          const SizedBox(height: 24),
        ],
      ),
    );
  }
}
