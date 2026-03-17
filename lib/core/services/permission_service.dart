import 'package:permission_handler/permission_handler.dart';
import 'package:flutter/foundation.dart';

class PermissionService {
  Future<bool> requestCameraPermission() async {
    final status = await Permission.camera.request();
    return status.isGranted;
  }

  Future<bool> requestBluetoothPermissions() async {
    if (defaultTargetPlatform == TargetPlatform.android) {
      final scan = await Permission.bluetoothScan.request();
      final connect = await Permission.bluetoothConnect.request();
      final location = await Permission.location.request();
      return scan.isGranted && connect.isGranted && location.isGranted;
    } else {
      final status = await Permission.bluetooth.request();
      return status.isGranted;
    }
  }

  Future<bool> hasAllPermissions() async {
    bool camera = await Permission.camera.isGranted;
    bool bt = false;
    if (defaultTargetPlatform == TargetPlatform.android) {
      bt = await Permission.bluetoothScan.isGranted && 
           await Permission.bluetoothConnect.isGranted &&
           await Permission.location.isGranted;
    } else {
      bt = await Permission.bluetooth.isGranted;
    }
    return camera && bt;
  }
}
