import 'package:flutter/material.dart';

class SafetyFooter extends StatelessWidget {
  final VoidCallback onEmergencyStop;

  const SafetyFooter({super.key, required this.onEmergencyStop});

  @override
  Widget build(BuildContext context) {
    return Container(
      width: double.infinity,
      decoration: const BoxDecoration(
        color: Color(0xFFFFC2BA), // Tertiary Container from design spec
        borderRadius: BorderRadius.horizontal(
          left: Radius.circular(32),
          right: Radius.circular(32),
        ),
      ),
      margin: const EdgeInsets.all(16),
      child: SafeArea(
        top: false,
        child: InkWell(
          onTap: onEmergencyStop,
          child: const Padding(
            padding: EdgeInsets.symmetric(vertical: 24),
            child: Text(
              'EMERGENCY STOP',
              textAlign: TextAlign.center,
              style: TextStyle(
                color: Color(0xFF690005), // onTertiaryFixed
                fontWeight: FontWeight.w900,
                fontSize: 24,
                letterSpacing: 2,
              ),
            ),
          ),
        ),
      ),
    );
  }
}
