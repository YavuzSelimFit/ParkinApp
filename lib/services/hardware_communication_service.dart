import 'dart:async';
import 'package:flutter/foundation.dart';
import 'package:flutter_reactive_ble/flutter_reactive_ble.dart';
import '../core/models/vehicle_state.dart';
import '../core/models/parking_space.dart';

class HardwareCommunicationService {
  final _ble = FlutterReactiveBle();
  StreamSubscription<ConnectionStateUpdate>? _connectionStream;
  StreamSubscription? _scanStream;
  String? _deviceId;
  
  static final Uuid serviceUuid = Uuid.parse("0000ffe0-0000-1000-8000-00805f9b34fb");
  static final Uuid commandCharUuid = Uuid.parse("0000ffe1-0000-1000-8000-00805f9b34fb");

  final _statusController = StreamController<VehicleStatus>.broadcast();
  Stream<VehicleStatus> get statusStream => _statusController.stream;

  final _dataController = StreamController<String>.broadcast();
  Stream<String> get receivedDataStream => _dataController.stream;

  StreamSubscription? _dataSubscription;

  void startScanning() {
    _scanStream?.cancel();
    _scanStream = _ble.scanForDevices(withServices: []).listen((device) {
      // Look for the Raspberry Pi 5 or other relevant devices
      final name = device.name.toLowerCase();
      if (name.contains("rpi") || name.contains("raspberry") || name.contains("car_v1") || name.contains("wattsnext")) {
        debugPrint('Vehicle Found: ${device.name} (${device.id})');
        _deviceId = device.id;
        _connect(device.id);
        _scanStream?.cancel();
      }
    });
  }

  void _connect(String deviceId) {
    _connectionStream?.cancel();
    _connectionStream = _ble.connectToDevice(
      id: deviceId,
      connectionTimeout: const Duration(seconds: 5),
    ).listen((update) {
      if (update.connectionState == DeviceConnectionState.connected) {
        _statusController.add(VehicleStatus.idle);
        
        // Subscribe to notifications from the Raspberry Pi
        _dataSubscription?.cancel();
        _dataSubscription = _ble.subscribeToCharacteristic(_commandCharacteristic).listen(
          (data) {
            final received = String.fromCharCodes(data).trim();
            debugPrint('Received from RPi: $received');
            
            if (received == "STATUS:ARRIVED") {
              _statusController.add(VehicleStatus.parkedSuccessfully);
            }
            
            _dataController.add(received);
          },
          onError: (e) => debugPrint('BLE Subscription Error: $e'),
        );
      } else if (update.connectionState == DeviceConnectionState.disconnected) {
        _statusController.add(VehicleStatus.disconnected);
        _dataSubscription?.cancel();
        _deviceId = null;
      }
    });
  }

  Future<void> sendParkCommand(ParkingSpace space) async {
    if (_deviceId == null) return;
    try {
      final data = "PARK:${space.qrValue}".codeUnits;
      await _ble.writeCharacteristicWithoutResponse(
        _commandCharacteristic,
        value: data,
      );
      debugPrint('[BLE] Sent: PARK:${space.qrValue}');
    } catch (e) {
      debugPrint('Park Command Send Error: $e');
    }
  }

  Future<void> sendSummonCommand(ParkingSpace homeSpace) async {
    if (_deviceId == null) return;
    final data = "SUMMON:${homeSpace.qrValue}".codeUnits;
    await _ble.writeCharacteristicWithoutResponse(
      _commandCharacteristic,
      value: data,
    );
  }

  QualifiedCharacteristic get _commandCharacteristic => QualifiedCharacteristic(
    characteristicId: commandCharUuid,
    serviceId: serviceUuid,
    deviceId: _deviceId!,
  );

  Future<void> sendRcCommand(double x, double y) async {
    if (_deviceId == null) return;
    try {
      final data = "RC:$x:$y".codeUnits;
      await _ble.writeCharacteristicWithoutResponse(
        _commandCharacteristic,
        value: data,
      );
    } catch (e) {
      debugPrint('RC Command Send Error: $e');
    }
  }

  Future<void> sendEmergencyStop() async {
    if (_deviceId == null) return;
    try {
      final data = "STOP".codeUnits;
      await _ble.writeCharacteristicWithoutResponse(
        _commandCharacteristic,
        value: data,
      );
    } catch (e) {
      debugPrint('Stop Command Error: $e');
    }
  }

  void dispose() {
    _scanStream?.cancel();
    _connectionStream?.cancel();
    _statusController.close();
    _dataController.close();
  }
}
