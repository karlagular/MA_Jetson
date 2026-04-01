"""Dummy alarm light — prints to console, no real hardware."""

from ports.alarm_light import AlarmLightPort


class DummyLight(AlarmLightPort):
    def turn_on(self) -> None:
        print("[AlarmLight] ON")

    def turn_off(self) -> None:
        print("[AlarmLight] OFF")
