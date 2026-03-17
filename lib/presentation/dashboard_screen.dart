import 'dart:math' as math;
import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../features/telemetry/presentation/telemetry_header.dart';
import '../features/scanner/presentation/aruco_scanner_view.dart';
import '../features/navigation/application/navigation_providers.dart';
import '../core/models/parking_space.dart';
import '../core/theme/app_theme.dart';

class DashboardScreen extends ConsumerStatefulWidget {
  const DashboardScreen({super.key});

  @override
  ConsumerState<DashboardScreen> createState() => _DashboardScreenState();
}

class _DashboardScreenState extends ConsumerState<DashboardScreen> {
  @override
  void initState() {
    super.initState();
    // Uygulama açıldığında otomatik olarak BLE izinlerini kontrol et ve taramayı başlat
    WidgetsBinding.instance.addPostFrameCallback((_) {
      _initializeConnection();
    });
  }

  Future<void> _initializeConnection() async {
    final hasPermissions = await ref.read(permissionServiceProvider).requestBluetoothPermissions();
    if (hasPermissions) {
      ref.read(hardwareServiceProvider).startScanning();
    }
  }

  @override
  Widget build(BuildContext context) {
    final slots = ref.watch(parkingSlotsProvider);
    
    return Scaffold(
      backgroundColor: const Color(0xFFF5F7F8), // Clean, modern light grey
      body: Stack(
        children: [
          SafeArea(
            child: Column(
              children: [
                const TelemetryHeader(
                  speed: 0.0,
                  battery: 85,
                  signal: 94,
                ),
                
                // Minimalist Horizontal Grid
                Expanded(
                  child: buildProfessionalParkingLayout(slots),
                ),
                
                // Bottom Spacing for Glass Footer
                const SizedBox(height: 100),
              ],
            ),
          ),

          // Bottom Action Shell (Glassmorphic)
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
                    color: const Color(0xEE1A1A1A), // Dark glass
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

  Widget buildProfessionalParkingLayout(List<ParkingSlot> slots) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 20.0),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: 24.0),
            child: Text(
              'PARK ALANLARI',
              style: GoogleFonts.spaceGrotesk(
                fontSize: 14,
                fontWeight: FontWeight.bold,
                color: Colors.grey.shade600,
                letterSpacing: 1.5,
              ),
            ),
          ),
          const SizedBox(height: 16),
          // Sağa sola kaydırılabilir alan burada başlıyor
          Expanded(
            child: GridView.builder(
              padding: const EdgeInsets.symmetric(horizontal: 24.0),
              scrollDirection: Axis.horizontal, // YATAY KAYDIRMA AÇIK
              gridDelegate: const SliverGridDelegateWithFixedCrossAxisCount(
                crossAxisCount: 2, // 2 Satır
                mainAxisSpacing: 16, // Yataydaki boşluklar
                crossAxisSpacing: 16, // Dikeydeki boşluklar
                childAspectRatio: 0.8, // Slot oranı
              ),
              itemCount: slots.length,
              itemBuilder: (context, index) {
                return CleanParkingSlotCard(
                  slotData: slots[index],
                  index: index,
                  onTap: () {
                    if (slots[index].isOccupied) {
                      _sendLocation(slots[index].space!);
                    } else {
                      _learnNewSlot(index);
                    }
                  },
                );
              },
            ),
          ),
        ],
      ),
    );
  }

  void _learnNewSlot(int index) {
    Navigator.of(context).push(
      MaterialPageRoute(
        builder: (context) => ArUcoScannerView(
          onResult: (arucoId) {
            ref.read(parkingSlotsProvider.notifier).assignQrToSlot(index, arucoId);
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

class CleanParkingSlotCard extends StatelessWidget {
  final ParkingSlot slotData;
  final int index;
  final VoidCallback onTap;

  const CleanParkingSlotCard({
    super.key,
    required this.slotData,
    required this.index,
    required this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    final isOccupied = slotData.isOccupied;
    final hasQrAssigned = slotData.hasQrAssigned;

    // Duruma göre renk ve sınır (border) ayarları
    Color bgColor = Colors.white;
    Color borderColor = Colors.grey.withValues(alpha: 0.1);
    double borderWidth = 1.0;
    Widget content = const SizedBox();

    if (isOccupied) {
      borderColor = AppColors.primary;
      borderWidth = 2.0;
      bgColor = AppColors.primary.withValues(alpha: 0.05);
      content = Column(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          const Icon(Icons.directions_car, size: 48, color: AppColors.primary),
          const SizedBox(height: 12),
          Text(
            'PARK EDİLDİ',
            style: GoogleFonts.inter(
              fontSize: 10,
              fontWeight: FontWeight.bold,
              color: AppColors.primary,
            ),
          ),
        ],
      );
    } else if (hasQrAssigned) {
      borderColor = const Color(0xFF34C759); // Apple Green
      borderWidth = 2.0;
      bgColor = const Color(0xFF34C759).withValues(alpha: 0.05);
      content = Column(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          const Icon(Icons.qr_code_scanner, size: 36, color: Color(0xFF34C759)),
          const SizedBox(height: 12),
          Text(
            'ARAÇ BEKLENİYOR',
            textAlign: TextAlign.center,
            style: GoogleFonts.inter(
              fontSize: 10,
              fontWeight: FontWeight.bold,
              color: const Color(0xFF34C759),
            ),
          ),
        ],
      );
    } else {
      content = Column(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          Icon(Icons.add_circle_outline, size: 32, color: Colors.grey.shade300),
          const SizedBox(height: 8),
          Text(
            'BOŞ',
            style: GoogleFonts.inter(
              fontSize: 10,
              fontWeight: FontWeight.w600,
              color: Colors.grey.shade400,
            ),
          ),
        ],
      );
    }

    return GestureDetector(
      onTap: onTap,
      child: AnimatedContainer(
        duration: const Duration(milliseconds: 300),
        decoration: BoxDecoration(
          color: bgColor,
          borderRadius: BorderRadius.circular(20),
          border: Border.all(color: borderColor, width: borderWidth),
          boxShadow: [
            BoxShadow(
              color: Colors.black.withValues(alpha: 0.02),
              blurRadius: 20,
              offset: const Offset(0, 10),
            ),
          ],
        ),
        child: Stack(
          children: [
            Positioned(
              top: 16,
              left: 16,
              child: Text(
                slotData.label,
                style: GoogleFonts.spaceGrotesk(
                  fontSize: 18,
                  fontWeight: FontWeight.bold,
                  color: isOccupied ? AppColors.primary : Colors.grey.shade800,
                ),
              ),
            ),
            Center(child: content),
          ],
        ),
      ),
    );
  }
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
