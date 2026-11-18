// Wi-Fi readings through CoreWLAN, for agent/device/sources/wifi.py.
//
// Why a compiled helper (wireless probe, 2026-11-17): system_profiler takes 12.6 s per reading and wdutil
// 6.3 s with sudo; CoreWLAN reads the link in about 2 ms without rights, and its scan gives the signal of
// every nearby network (system_profiler gave it for 1 of 9). Compiled once with swiftc into logs/bin/.
//
//   wifi_helper link                 one JSON line: the current link
//   wifi_helper watch <hz> <seconds> one JSON line per reading
//   wifi_helper scan                 one JSON line per network seen (takes about 13 s)
//   wifi_helper serve                reads commands from stdin: "scan" prints the networks and then END; "quit" stops.
//                                    Run through the Swift interpreter, it names the networks (the compiled helper does
//                                    not) and pays the interpreter's start-up once per walk instead of once per scan.

import CoreWLAN
import Foundation

let bands: [Int: String] = [1: "2.4", 2: "5", 3: "6"]
let widths: [Int: Int] = [1: 20, 2: 40, 3: 80, 4: 160]

func channel(_ c: CWChannel?) -> [String: Any] {
    guard let c = c else { return [:] }
    return ["channel": c.channelNumber, "band_ghz": bands[c.channelBand.rawValue] ?? "?",
            "width_mhz": widths[c.channelWidth.rawValue] ?? 0]
}

func emit(_ record: [String: Any]) {
    if let data = try? JSONSerialization.data(withJSONObject: record), let text = String(data: data, encoding: .utf8) {
        print(text)
        fflush(stdout)
    }
}

guard let wifi = CWWiFiClient.shared().interface() else {
    emit(["error": "no Wi-Fi interface"])
    exit(1)
}

func link() -> [String: Any] {
    var record: [String: Any] = ["t": Date().timeIntervalSince1970, "rssi_dbm": wifi.rssiValue(),
                                 "noise_dbm": wifi.noiseMeasurement(), "tx_mbps": wifi.transmitRate(),
                                 "phy": wifi.activePHYMode().rawValue, "power_on": wifi.powerOn()]
    for (key, value) in channel(wifi.wlanChannel()) { record[key] = value }
    return record
}

func scanAll() -> Bool {
    do {
        for n in try wifi.scanForNetworks(withSSID: nil) {
            var record: [String: Any] = ["rssi_dbm": n.rssiValue, "noise_dbm": n.noiseMeasurement, "ssid": n.ssid ?? "",
                                         "bssid": n.bssid ?? "", "beacon_ms": n.beaconInterval,
                                         "open": n.supportsSecurity(.none)]
            for (key, value) in channel(n.wlanChannel) { record[key] = value }
            emit(record)
        }
        return true
    } catch {
        emit(["error": "\(error)"])
        return false
    }
}

let args = CommandLine.arguments
switch args.count > 1 ? args[1] : "link" {
case "watch":
    let hz = args.count > 2 ? Double(args[2]) ?? 10 : 10
    let seconds = args.count > 3 ? Double(args[3]) ?? 10 : 10
    let end = Date().addingTimeInterval(seconds)
    while Date() < end {
        emit(link())
        Thread.sleep(forTimeInterval: 1.0 / hz)
    }
case "scan":
    if !scanAll() { exit(1) }
case "serve":
    while let line = readLine() {
        if line == "quit" { break }
        if line == "scan" {
            _ = scanAll()
            print("END")
            fflush(stdout)
        }
    }
default:
    emit(link())
}
