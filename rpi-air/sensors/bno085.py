import board
import busio
import adafruit_bno08x
from adafruit_bno08x.i2c import BNO08X_I2C
from dataclasses import dataclass


@dataclass
class Bno085Data:
    roll_deg: float = 0.0
    pitch_deg: float = 0.0
    yaw_deg: float = 0.0
    accel_x: float = 0.0
    accel_y: float = 0.0
    accel_z: float = 0.0


class Bno085Sensor:
    def __init__(self):
        i2c = busio.I2C(board.SCL, board.SDA)
        self._imu = BNO08X_I2C(i2c)
        self._imu.enable_feature(adafruit_bno08x.BNO_REPORT_ROTATION_VECTOR)
        self._imu.enable_feature(adafruit_bno08x.BNO_REPORT_ACCELEROMETER)

    def read(self) -> Bno085Data:
        import math
        quat = self._imu.quaternion
        accel = self._imu.acceleration

        if quat is None:
            return Bno085Data()

        qw, qx, qy, qz = quat
        roll = math.degrees(math.atan2(2*(qw*qx + qy*qz), 1 - 2*(qx**2 + qy**2)))
        pitch = math.degrees(math.asin(max(-1, min(1, 2*(qw*qy - qz*qx)))))
        yaw = math.degrees(math.atan2(2*(qw*qz + qx*qy), 1 - 2*(qy**2 + qz**2)))

        ax, ay, az = accel if accel else (0, 0, 0)
        return Bno085Data(
            roll_deg=round(roll, 2),
            pitch_deg=round(pitch, 2),
            yaw_deg=round(yaw, 2),
            accel_x=round(ax, 3),
            accel_y=round(ay, 3),
            accel_z=round(az, 3),
        )
