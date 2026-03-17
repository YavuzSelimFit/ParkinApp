import 'package:flutter/material.dart';
import 'package:mobile_scanner/mobile_scanner.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../../../core/theme/app_theme.dart';

class QRScannerOverlay extends ConsumerStatefulWidget {
  final Function(String)? onResult;
  const QRScannerOverlay({super.key, this.onResult});

  @override
  ConsumerState<QRScannerOverlay> createState() => _QRScannerOverlayState();
}

class _QRScannerOverlayState extends ConsumerState<QRScannerOverlay> {
  bool _isProcessing = false;

  void _handleCapture(BarcodeCapture capture) {
    if (_isProcessing) return;
    
    final List<Barcode> barcodes = capture.barcodes;
    if (barcodes.isNotEmpty && barcodes.first.rawValue != null) {
      setState(() => _isProcessing = true);
      final qrValue = barcodes.first.rawValue!;

      if (widget.onResult != null) {
        widget.onResult!(qrValue);
      } else {
        Navigator.pop(context);
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: Colors.black,
      body: Stack(
        children: [
          MobileScanner(
            onDetect: _handleCapture,
          ),
          Center(
            child: Container(
              width: 250,
              height: 250,
              decoration: BoxDecoration(
                border: Border.all(color: AppColors.primary, width: 2),
                borderRadius: BorderRadius.circular(32),
              ),
              child: _isProcessing 
                ? const Center(child: CircularProgressIndicator(color: AppColors.primary))
                : const SizedBox.shrink(),
            ),
          ),
          Positioned(
            top: 48,
            left: 24,
            child: IconButton(
              icon: const Icon(Icons.arrow_back_ios_new, color: Colors.white),
              onPressed: () => Navigator.pop(context),
            ),
          ),
          const Positioned(
            bottom: 80,
            left: 0,
            right: 0,
            child: Center(
              child: Text(
                'SCAN QR TO ASSIGN SLOT',
                style: TextStyle(
                  color: Colors.white70,
                  fontFamily: 'SpaceGrotesk',
                  fontWeight: FontWeight.bold,
                  letterSpacing: 2,
                ),
              ),
            ),
          ),
        ],
      ),
    );
  }
}
