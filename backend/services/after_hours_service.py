from datetime import datetime, time


class AfterHoursService:
    def __init__(self):
        self.start_time = time(6, 0)
        self.end_time = time(20, 0)

    def check_after_hours(self, current_time=None):
        if current_time is None:
            current_time = datetime.now().time()

        after_hours = not (
            self.start_time <= current_time <= self.end_time
        )

        return {
            "after_hours": after_hours,
            "message": (
                "Activity detected after campus hours"
                if after_hours
                else "Within campus hours"
            )
        }