import 'dart:math' as math;
import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../features/telemetry/presentation/telemetry_header.dart';
import '../features/scanner/presentation/qr_scanner_overlay.dart';
import '../features/navigation/application/navigation_providers.dart';
import '../core/theme/app_theme.dart';
import '../core/models/parking_space.dart';

class DashboardScreen extends ConsumerStatefulWidget {
  const DashboardScreen({super.key});

  @override
  ConsumerState<DashboardScreen> createState() => _DashboardScreenState();
}

class _DashboardScreenState extends ConsumerState<DashboardScreen> with SingleTickerProviderStateMixin {
  bool _permissionsGranted = false;
  late AnimationController _floatController;

  @override
  void initState() {
    super.initState();
    _checkPermissions();
    _floatController = AnimationController(
      vsync: this,
      duration: const Duration(seconds: 3),
    )..repeat(reverse: true);
  }

  @override
  void dispose() {
    _floatController.dispose();
    super.dispose();
  }

  Future<void> _checkPermissions() async {
    final ps = ref.read(permissionServiceProvider);
    bool granted = await ps.hasAllPermissions();
    if (!granted) {
      granted = await ps.requestCameraPermission() && 
                await ps.requestBluetoothPermissions();
    }
    if (mounted) {
      setState(() => _permissionsGranted = granted);
      if (granted) {
        ref.read(hardwareServiceProvider).startScanning();
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    ref.watch(vehicleStatusListenerProvider);

    if (!_permissionsGranted) {
      return const Scaffold(
        backgroundColor: AppColors.canvas,
        body: Center(child: CircularProgressIndicator(color: AppColors.primary)),
      );
    }

    final slots = ref.watch(parkingSlotsProvider);

    return Scaffold(
      backgroundColor: const Color(0xFFFCFDFD), // Clean Urban Park background
      body: Stack(
        children: [
          SafeArea(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.center,
              children: [
                const SizedBox(height: 32),
                Padding(
                  padding: const EdgeInsets.symmetric(horizontal: 24.0),
                  child: Row(
                    mainAxisAlignment: MainAxisAlignment.spaceBetween,
                    children: [
                      Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          const Text(
                            'URBAN PARK',
                            style: TextStyle(
                              color: AppColors.primary,
                              fontFamily: 'SpaceGrotesk',
                              fontSize: 24,
                              fontWeight: FontWeight.w900,
                              letterSpacing: -0.5,
                            ),
                          ),
                          Container(
                            height: 2,
                            width: 20,
                            color: AppColors.primary,
                          ),
                        ],
                      ),
                      StatusIndicator(),
                    ],
                  ),
                ),
                const SizedBox(height: 48),
                const Text(
                  'FIND YOUR SPOT',
                  style: TextStyle(
                    color: Colors.black,
                    fontFamily: 'PlusJakartaSans',
                    fontSize: 32,
                    fontWeight: FontWeight.w800,
                    letterSpacing: -1,
                  ),
                ),
                const Text(
                  'Select a glowing emerald space to begin',
                  style: TextStyle(
                    color: Colors.black45,
                    fontSize: 14,
                  ),
                ),
                
                // 3D Isometric View
                Expanded(
                  child: Center(
                    child: Transform(
                      transform: Matrix4.identity()
                        ..setEntry(3, 2, 0.001)
                        ..rotateX(45 * math.pi / 180)
                        ..rotateZ(-35 * math.pi / 180),
                      alignment: Alignment.center,
                      child: Padding(
                        padding: const EdgeInsets.all(48.0),
                        child: Wrap(
                          spacing: 40,
                          runSpacing: 60,
                          children: List.generate(slots.length, (index) {
                            final slot = slots[index];
                            return _IsometricParkingSlot(
                              slot: slot,
                              floatAnimation: _floatController,
                              onTap: () {
                                if (slot.isOccupied) {
                                  _sendLocation(slot.space!);
                                } else {
                                  _learnNewSlot(index);
                                }
                              },
                            );
                          }),
                        ),
                      ),
                    ),
                  ),
                ),
              ],
            ),
          ),
          // Bottom Action Shell
          Positioned(
            left: 0,
            right: 0,
            bottom: 32,
            child: Center(
              child: ClipRRect(
                borderRadius: BorderRadius.circular(32),
                child: Container(
                  width: math.min(MediaQuery.of(context).size.width - 48, 400),
                  padding: const EdgeInsets.all(8),
                  decoration: BoxDecoration(
                    color: const Color(0xEE1A1A1A), // Dark glass effect
                    borderRadius: BorderRadius.circular(32),
                    border: Border.all(color: const Color(0x0DFFFFFF)),
                  ),
                  child: Row(
                    children: [
                      Expanded(
                        child: _NavButtonV2(
                          label: 'SUMMON',
                          icon: Icons.rocket_launch,
                          color: const Color(0xFF00E5FF),
                          textColor: Colors.black,
                          onPressed: () => _summonVehicle(),
                        ),
                      ),
                      const SizedBox(width: 8),
                      Expanded(
                        child: _NavButtonV2(
                          label: 'STOP',
                          icon: Icons.report_problem,
                          color: const Color(0x0DFFFFFF),
                          textColor: const Color(0xFFFF453A),
                          onPressed: () => ref.read(hardwareServiceProvider).sendEmergencyStop(),
                        ),
                      ),
                    ],
                  ),
                ),
              ),
            ),
          ),
        ],
      ),
    );
  }

  void _learnNewSlot(int index) {
    Navigator.of(context).push(
      MaterialPageRoute(
        builder: (context) => QRScannerOverlay(
          onResult: (qrValue) {
            ref.read(parkingSlotsProvider.notifier).updateSlot(index, qrValue);
            Navigator.pop(context);
          },
        ),
      ),
    );
  }

  void _summonVehicle() {
    _sendLocation(const ParkingSpace(
      id: 'summon',
      label: 'HOME',
      qrValue: 'ORIGIN_00',
      coordinates: [0, 0],
    ));
  }

  void _sendLocation(ParkingSpace space) {
    if (!ref.read(isConnectedProvider)) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          content: Text('VEHICLE OFFLINE'),
          backgroundColor: Colors.black,
          behavior: SnackBarBehavior.floating,
        ),
      );
      return;
    }
    ref.read(hardwareServiceProvider).sendParkCommand(space);
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text('SENDING TARGET: ${space.label.toUpperCase()}'),
        backgroundColor: AppColors.primary,
        behavior: SnackBarBehavior.floating,
      ),
    );
  }
}

class _IsometricParkingSlot extends StatelessWidget {
  final ParkingSlot slot;
  final Animation<double> floatAnimation;
  final VoidCallback onTap;

  const _IsometricParkingSlot({
    required this.slot,
    required this.floatAnimation,
    required this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: onTap,
      child: SizedBox(
        width: 100,
        height: 150,
        child: Stack(
          alignment: Alignment.center,
          clipBehavior: Clip.none,
          children: [
            CustomPaint(
              size: const Size(80, 120),
              painter: _SlabPainter(
                isOccupied: slot.isOccupied,
                color: slot.isOccupied ? const Color(0xFFF1FDF6) : const Color(0xFFEEF2F3),
              ),
            ),
            Transform(
              transform: Matrix4.identity()
                ..rotateZ(35 * math.pi / 180)
                ..rotateX(-45 * math.pi / 180),
              alignment: Alignment.center,
              child: AnimatedBuilder(
                animation: floatAnimation,
                builder: (context, child) {
                  final floatOffset = slot.isOccupied ? 0.0 : floatAnimation.value * 15.0;
                  return Transform.translate(
                    offset: Offset(0, -30 - floatOffset),
                    child: child,
                  );
                },
                child: slot.isOccupied 
                  ? Column(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        const Icon(Icons.check_circle, color: AppColors.primary, size: 24),
                        const SizedBox(height: 4),
                        Text(
                          slot.label,
                          style: GoogleFonts.spaceGrotesk(
                            color: AppColors.primary,
                            fontWeight: FontWeight.w900,
                            fontSize: 10,
                          ),
                        ),
                      ],
                    )
                  : Container(
                      padding: const EdgeInsets.all(8),
                      decoration: const BoxDecoration(
                        gradient: LinearGradient(
                          colors: [Color(0xFF006D43), Color(0xFF00A86B)],
                          begin: Alignment.topLeft,
                          end: Alignment.bottomRight,
                        ),
                        shape: BoxShape.circle,
                        boxShadow: [
                          BoxShadow(
                            color: Color(0x6600A86B),
                            blurRadius: 15,
                            spreadRadius: 2,
                          )
                        ],
                      ),
                      child: const Icon(Icons.add, color: Colors.white, size: 20),
                    ),
              ),
            ),
            if (!slot.isOccupied)
              Positioned(
                bottom: -20,
                child: Transform(
                  transform: Matrix4.identity()
                    ..rotateZ(35 * math.pi / 180)
                    ..rotateX(-45 * math.pi / 180),
                  alignment: Alignment.center,
                  child: Text(
                    slot.label,
                    style: GoogleFonts.spaceGrotesk(
                      color: Colors.black26,
                      fontWeight: FontWeight.w800,
                      fontSize: 10,
                    ),
                  ),
                ),
              ),
          ],
        ),
      ),
    );
  }
}

class _SlabPainter extends CustomPainter {
  final bool isOccupied;
  final Color color;

  _SlabPainter({required this.isOccupied, required this.color});

  @override
  void paint(Canvas canvas, Size size) {
    final paint = Paint()
      ..color = color
      ..style = PaintingStyle.fill;

    final borderPaint = Paint()
      ..color = isOccupied ? const Color(0xFFA7F3D0) : const Color(0xFFDAE1E3)
      ..style = PaintingStyle.stroke
      ..strokeWidth = 2;

    final depthPaintSide = Paint()..color = const Color(0xFFB0BEC5);
    final depthPaintBottom = Paint()..color = const Color(0xFFCFD8DC);

    final rect = RRect.fromRectAndRadius(
      Rect.fromLTWH(0, 0, size.width, size.height),
      const Radius.circular(4),
    );

    final sidePath = Path()
      ..moveTo(size.width, 0)
      ..lineTo(size.width + 8, 8)
      ..lineTo(size.width + 8, size.height + 8)
      ..lineTo(size.width, size.height)
      ..close();
    canvas.drawPath(sidePath, depthPaintSide);

    final bottomPath = Path()
      ..moveTo(0, size.height)
      ..lineTo(8, size.height + 8)
      ..lineTo(size.width + 8, size.height + 8)
      ..lineTo(size.width, size.height)
      ..close();
    canvas.drawPath(bottomPath, depthPaintBottom);

    canvas.drawRRect(rect, paint);
    canvas.drawRRect(rect, borderPaint);
  }

  @override
  bool shouldRepaint(covariant CustomPainter oldDelegate) => false;
}

class _NavButtonV2 extends StatelessWidget {
  final String label;
  final IconData icon;
  final Color color;
  final Color textColor;
  final VoidCallback onPressed;

  const _NavButtonV2({
    required this.label,
    required this.icon,
    required this.color,
    required this.textColor,
    required this.onPressed,
  });

  @override
  Widget build(BuildContext context) {
    return InkWell(
      onTap: onPressed,
      borderRadius: BorderRadius.circular(24),
      child: Container(
        height: 56,
        decoration: BoxDecoration(
          color: color,
          borderRadius: BorderRadius.circular(24),
        ),
        child: Row(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Icon(icon, color: textColor, size: 18),
            const SizedBox(width: 8),
            Text(
              label,
              style: GoogleFonts.spaceGrotesk(
                color: textColor,
                fontWeight: FontWeight.bold,
                fontSize: 13,
                letterSpacing: 1.2,
              ),
            ),
          ],
        ),
      ),
    );
  }
}
