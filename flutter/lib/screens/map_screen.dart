import 'package:flutter/material.dart';
import 'package:flutter_map/flutter_map.dart';
import 'package:latlong2/latlong.dart';
import 'package:provider/provider.dart';
import '../services/telemetry_service.dart';
import '../models/telemetry.dart';

class MapScreen extends StatelessWidget {
  const MapScreen({super.key});

  @override
  Widget build(BuildContext context) {
    final svc = context.watch<TelemetryService>();
    final points = svc.history
        .where((t) => t.lat != null && t.lon != null)
        .map((t) => LatLng(t.lat!, t.lon!))
        .toList();
    final latest = svc.latest;
    final center = points.isNotEmpty ? points.last : const LatLng(52.2297, 21.0122);

    return Scaffold(
      backgroundColor: const Color(0xFF0D1117),
      appBar: AppBar(
        backgroundColor: const Color(0xFF161B22),
        title: const Text('Mapa lotu', style: TextStyle(color: Colors.white)),
        actions: [
          if (latest?.alt != null)
            Padding(
              padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
              child: Text(
                '${latest!.alt!.toStringAsFixed(0)} m n.p.m.',
                style: const TextStyle(color: Colors.cyanAccent, fontWeight: FontWeight.bold),
              ),
            ),
        ],
      ),
      body: FlutterMap(
        options: MapOptions(initialCenter: center, initialZoom: 11),
        children: [
          TileLayer(
            urlTemplate: 'https://tile.openstreetmap.org/{z}/{x}/{y}.png',
            userAgentPackageName: 'com.stratosteam.app',
          ),
          if (points.length > 1)
            PolylineLayer(polylines: [
              Polyline(points: points, color: Colors.cyanAccent, strokeWidth: 2.5),
            ]),
          if (points.isNotEmpty)
            MarkerLayer(markers: [
              // start
              Marker(
                point: points.first,
                width: 20,
                height: 20,
                child: const Icon(Icons.trip_origin, color: Colors.greenAccent, size: 20),
              ),
              // current
              Marker(
                point: points.last,
                width: 32,
                height: 32,
                child: Container(
                  decoration: BoxDecoration(
                    shape: BoxShape.circle,
                    color: Colors.redAccent.withOpacity(0.2),
                    border: Border.all(color: Colors.redAccent, width: 2),
                  ),
                  child: const Icon(Icons.navigation, color: Colors.redAccent, size: 18),
                ),
              ),
            ]),
        ],
      ),
      floatingActionButton: points.isNotEmpty
          ? FloatingActionButton.small(
              backgroundColor: const Color(0xFF161B22),
              onPressed: () {},   // MapController.move — TODO if needed
              child: const Icon(Icons.my_location, color: Colors.cyanAccent),
            )
          : null,
    );
  }
}
