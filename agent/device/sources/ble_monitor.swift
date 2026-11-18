// Bluetooth Low Energy advertisements heard by the Mac, for the coverage walk (agent/device/sources/ble.py).
//
// Why (2026-11-18): system_profiler gives no signal for a connected Bluetooth speaker (classic audio), so the
// walk follows a device that advertises over BLE instead (an iPhone near the router was heard at -37 dBm).
//
//   swift ble_monitor.swift <seconds>     one line per advertisement: t=<unix time> rssi=<dBm> name=<name>

import CoreBluetooth
import Foundation

class Monitor: NSObject, CBCentralManagerDelegate {
    var manager: CBCentralManager!
    override init() {
        super.init()
        manager = CBCentralManager(delegate: self, queue: nil)
    }
    func centralManagerDidUpdateState(_ central: CBCentralManager) {
        print("state=\(central.state.rawValue)")
        fflush(stdout)
        if central.state == .poweredOn {
            central.scanForPeripherals(withServices: nil, options: [CBCentralManagerScanOptionAllowDuplicatesKey: true])
        }
    }
    func centralManager(_ central: CBCentralManager, didDiscover p: CBPeripheral, advertisementData: [String: Any], rssi: NSNumber) {
        let name = (advertisementData[CBAdvertisementDataLocalNameKey] as? String) ?? p.name ?? ""
        print("t=\(Date().timeIntervalSince1970) rssi=\(rssi) id=\(p.identifier.uuidString.prefix(8)) name=\(name)")
        fflush(stdout)
    }
}

let seconds = CommandLine.arguments.count > 1 ? Double(CommandLine.arguments[1]) ?? 3600 : 3600
let monitor = Monitor()
RunLoop.main.run(until: Date().addingTimeInterval(seconds))
