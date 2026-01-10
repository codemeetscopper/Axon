#!/usr/bin/env python3
import time
import argparse
from axon_chassis_service.panandtilt.controller import PanTiltController, ServoCalibration


def sweep_once(ctl: PanTiltController, delay: float = 0.2):
    # safe-ish default sweep (avoid hitting mechanical stops)
    path = [
        (90, 90),
        (90, 180),
        (90, 60),
        (0, 90),
        (180, 90),
        (90, 90),
    ]
    for pan, tilt in path:
        ctl.set_angles(pan, tilt, smooth=True)
        time.sleep(delay)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--addr", type=lambda x: int(x, 0), default="0x40")
    ap.add_argument("--pan-ch", type=int, default=0)
    ap.add_argument("--tilt-ch", type=int, default=1)

    ap.add_argument("--min-us", type=int, default=500)
    ap.add_argument("--max-us", type=int, default=2500)

    ap.add_argument("--invert-pan", action="store_true")
    ap.add_argument("--invert-tilt", action="store_true")

    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("center")

    p_set = sub.add_parser("set")
    p_set.add_argument("pan", type=float)
    p_set.add_argument("tilt", type=float)
    p_set.add_argument("--nosmooth", action="store_true")

    p_sweep = sub.add_parser("sweep")
    p_sweep.add_argument("--loop", action="store_true")
    p_sweep.add_argument("--delay", type=float, default=0.2)

    args = ap.parse_args()

    ctl = PanTiltController(
        i2c_address=args.addr,
        pan_channel=args.pan_ch,
        tilt_channel=args.tilt_ch,
        pan_cal=ServoCalibration(args.min_us, args.max_us),
        tilt_cal=ServoCalibration(args.min_us, args.max_us),
        invert_pan=args.invert_pan,
        invert_tilt=args.invert_tilt,
    )

    try:
        if args.cmd == "center":
            ctl.set_angles(90, 90, smooth=True)

        elif args.cmd == "set":
            ctl.set_angles(args.pan, args.tilt, smooth=not args.nosmooth)

        elif args.cmd == "sweep":
            if args.loop:
                while True:
                    sweep_once(ctl, delay=args.delay)
            else:
                sweep_once(ctl, delay=args.delay)

    except KeyboardInterrupt:
        pass
    finally:
        # optional: go back to center before exit
        try:
            ctl.set_angles(90, 60, smooth=True)
        except Exception:
            pass
        ctl.close()


if __name__ == "__main__":
    main()
