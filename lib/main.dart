import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'core/theme/app_theme.dart';
import 'presentation/dashboard_screen.dart';

void main() {
  runApp(
    const ProviderScope(
      child: IntelligentParkingApp(),
    ),
  );
}

class IntelligentParkingApp extends StatelessWidget {
  const IntelligentParkingApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'Intelligent Parking App',
      debugShowCheckedModeBanner: false,
      theme: AppTheme.kineticCockpit,
      home: const DashboardScreen(),
    );
  }
}
