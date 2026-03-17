import 'package:flutter/material.dart';
import 'package:camera/camera.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../application/aruco_scanner_service.dart';
import '../../navigation/application/navigation_providers.dart';
import '../../../core/theme/app_theme.dart';

class ArUcoScannerView extends ConsumerStatefulWidget {
  final Function(String)? onResult;
  const ArUcoScannerView({super.key, this.onResult});

  @override
  ConsumerState<ArUcoScannerView> createState() => _ArUcoScannerViewState();
}

class _ArUcoScannerViewState extends ConsumerState<ArUcoScannerView> {
  CameraController? _controller;
  bool _isProcessing = false;
  late ArucoScannerService _scannerService;

  @override
  void initState() {
    super.initState();
    _scannerService = ref.read(arucoScannerServiceProvider);
    _scannerService.initialize();
    _initializeCamera();
  }

  Future<void> _initializeCamera() async {
    final cameras = await availableCameras();
    if (cameras.isEmpty) return;

    _controller = CameraController(
      cameras.first,
      ResolutionPreset.high,
      enableAudio: false,
      imageFormatGroup: ImageFormatGroup.bgra8888,
    );

    try {
      await _controller!.initialize();
      if (!mounted) return;
      
      _controller!.startImageStream((image) {
        if (_isProcessing) return;
        _processFrame(image);
      });
      
      setState(() {});
    } catch (e) {
      debugPrint("Camera Init Error: $e");
    }
  }

  void _processFrame(CameraImage image) {
    if (_isProcessing) return;

    final result = _scannerService.detectFromImage(image);
    
    if (result != null) {
      setState(() => _isProcessing = true);
      
      if (widget.onResult != null) {
        widget.onResult!(result);
      } else {
        Navigator.pop(context, result);
      }
    }
  }

  @override
  void dispose() {
    _controller?.dispose();
    _scannerService.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    if (_controller == null || !_controller!.value.isInitialized) {
      return const Scaffold(
        backgroundColor: Colors.black,
        body: Center(child: CircularProgressIndicator(color: AppColors.primary)),
      );
    }

    return Scaffold(
      backgroundColor: Colors.black,
      body: Stack(
        fit: StackFit.expand,
        children: [
          CameraPreview(_controller!),
          
          // Scanning Overlay
          Center(
            child: Container(
              width: 250,
              height: 250,
              decoration: BoxDecoration(
                border: Border.all(color: AppColors.primary, width: 2),
                borderRadius: BorderRadius.circular(12),
              ),
              child: _isProcessing 
                ? const Center(child: CircularProgressIndicator(color: AppColors.primary))
                : const SizedBox.shrink(),
            ),
          ),

          // Back Button
          Positioned(
            top: 48,
            left: 24,
            child: IconButton(
              icon: const Icon(Icons.arrow_back_ios_new, color: Colors.white),
              onPressed: () => Navigator.pop(context),
            ),
          ),

          // Label
          const Positioned(
            bottom: 80,
            left: 0,
            right: 0,
            child: Center(
              child: Text(
                'POINT AT ARUCO MARKER (DICT_6X6_250)',
                style: TextStyle(
                  color: Colors.white70,
                  fontSize: 12,
                  fontWeight: FontWeight.bold,
                  letterSpacing: 1.5,
                ),
              ),
            ),
          ),
        ],
      ),
    );
  }
}
