class Telemetry {
  final int id;
  final int seq;
  final int ts;
  final DateTime receivedAt;
  final int rssi;
  final double snr;

  // GPS
  final double? lat;
  final double? lon;
  final double? alt;
  final double? speedKmh;
  final int satellites;
  final bool gpsFix;

  // BME280
  final double bmeTemp;
  final double bmeHum;
  final double bmePres;

  // MS5611
  final double msTemp;
  final double msPres;
  final double msAlt;

  // BNO085
  final double roll;
  final double pitch;
  final double yaw;

  // INA219
  final double voltage;
  final double currentMa;
  final double powerMw;

  const Telemetry({
    required this.id,
    required this.seq,
    required this.ts,
    required this.receivedAt,
    required this.rssi,
    required this.snr,
    this.lat,
    this.lon,
    this.alt,
    this.speedKmh,
    required this.satellites,
    required this.gpsFix,
    required this.bmeTemp,
    required this.bmeHum,
    required this.bmePres,
    required this.msTemp,
    required this.msPres,
    required this.msAlt,
    required this.roll,
    required this.pitch,
    required this.yaw,
    required this.voltage,
    required this.currentMa,
    required this.powerMw,
  });

  factory Telemetry.fromJson(Map<String, dynamic> j) => Telemetry(
        id: j['id'] ?? 0,
        seq: j['seq'] ?? 0,
        ts: j['ts'] ?? 0,
        receivedAt: DateTime.tryParse(j['received_at'] ?? '') ?? DateTime.now(),
        rssi: j['rssi'] ?? 0,
        snr: (j['snr'] ?? 0).toDouble(),
        lat: (j['lat'] as num?)?.toDouble(),
        lon: (j['lon'] as num?)?.toDouble(),
        alt: (j['alt'] as num?)?.toDouble(),
        speedKmh: (j['speed_kmh'] as num?)?.toDouble(),
        satellites: j['satellites'] ?? 0,
        gpsFix: j['gps_fix'] ?? false,
        bmeTemp: (j['bme_temp'] ?? 0).toDouble(),
        bmeHum: (j['bme_hum'] ?? 0).toDouble(),
        bmePres: (j['bme_pres'] ?? 0).toDouble(),
        msTemp: (j['ms_temp'] ?? 0).toDouble(),
        msPres: (j['ms_pres'] ?? 0).toDouble(),
        msAlt: (j['ms_alt'] ?? 0).toDouble(),
        roll: (j['roll'] ?? 0).toDouble(),
        pitch: (j['pitch'] ?? 0).toDouble(),
        yaw: (j['yaw'] ?? 0).toDouble(),
        voltage: (j['voltage'] ?? 0).toDouble(),
        currentMa: (j['current_ma'] ?? 0).toDouble(),
        powerMw: (j['power_mw'] ?? 0).toDouble(),
      );
}
