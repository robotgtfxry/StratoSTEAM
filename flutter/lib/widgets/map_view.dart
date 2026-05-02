import 'package:flutter/material.dart';
import 'package:flutter_map/flutter_map.dart';
import 'package:latlong2/latlong.dart';
import '../models/telemetry.dart';

class MapView extends StatelessWidget {
  final List<Telemetry> history;
  const MapView({super.key, required this.history});

  @override
  Widget build(BuildContext context) {
    final points = history
        .where((t) => t.lat != null && t.lon != null)
        .map((t) => LatLng(t.lat!, t.lon!))
        .toList();

    final center = points.isNotEmpty ? points.last : const LatLng(52.2297, 21.0122); // Warsaw default

    return ClipRRect(
      borderRadius: BorderRadius.circular(10),
      child: FlutterMap(
        options: MapOptions(initialCenter: center, initialZoom: 10),
        children: [
          TileLayer(
            urlTemplate: 'https://tile.openstreetmap.org/{z}/{x}/{y}.png',
            userAgentPackageName: 'com.stratosteam.app',
          ),
          if (points.length > 1)
            PolylineLayer(polylines: [
              Polyline(points: points, color: Colors.cyanAccent, strokeWidth: 2),
            ]),
          if (points.isNotEmpty)
            MarkerLayer(markers: [
              Marker(
                point: points.last,
                width: 24,
                height: 24,
                child: const Icon(Icons.location_on, color: Colors.redAccent, size: 24),
              ),
            ]),
        ],
      ),
    );
  }
}
