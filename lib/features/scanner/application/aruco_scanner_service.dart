import 'dart:ffi' as ffi;
import 'package:ffi/ffi.dart';
import 'package:camera/camera.dart';
import 'package:flutter/foundation.dart';
import 'package:opencv_dart/opencv_dart.dart' as cv;

class ArucoScannerService {
  cv.ArucoDetector? _detector;
  bool _isInitialized = false;
  
  // Use a dedicated buffer to avoid constant reallocation
  ffi.Pointer<ffi.Uint8>? _imageBuffer;
  int _currentBufferSize = 0;

  void initialize() {
    if (_isInitialized) return;
    final dictionary = cv.ArucoDictionary.predefined(cv.PredefinedDictionaryType.DICT_6X6_250);
    final parameters = cv.ArucoDetectorParameters.empty();
    _detector = cv.ArucoDetector.create(dictionary, parameters);
    _isInitialized = true;
  }

  String? detectFromImage(CameraImage image) {
    if (!_isInitialized || _detector == null) return null;

    try {
      final totalBytes = image.planes[0].bytes.length;
      
      // Ensure buffer is large enough
      if (_imageBuffer == null || _currentBufferSize < totalBytes) {
        if (_imageBuffer != null) calloc.free(_imageBuffer!);
        _imageBuffer = calloc<ffi.Uint8>(totalBytes);
        _currentBufferSize = totalBytes;
      }

      // Copy bytes to native memory
      final Uint8List nativeList = _imageBuffer!.asTypedList(totalBytes);
      nativeList.setAll(0, image.planes[0].bytes);

      cv.Mat? mat;
      
      if (image.format.group == ImageFormatGroup.bgra8888) {
        mat = cv.Mat.fromBuffer(
          image.height,
          image.width,
          cv.MatType.CV_8UC4,
          _imageBuffer!.cast<ffi.Void>(),
        );
      } else if (image.format.group == ImageFormatGroup.yuv420) {
        mat = cv.Mat.fromBuffer(
          image.height,
          image.width,
          cv.MatType.CV_8UC1,
          _imageBuffer!.cast<ffi.Void>(),
        );
      }

      if (mat == null || mat.isEmpty) return null;

      final (corners, ids, _) = _detector!.detectMarkers(mat);
      
      if (ids.isNotEmpty) {
        return ids.first.toString();
      }
    } catch (e) {
      debugPrint("ArUco Detection Error: $e");
    }
    return null;
  }

  void dispose() {
    _isInitialized = false;
    if (_imageBuffer != null) {
      calloc.free(_imageBuffer!);
      _imageBuffer = null;
    }
  }
}
