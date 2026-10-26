class LoiteringService:
    def __init__(self, threshold=30, distance=150):
        self.threshold = threshold
        self.distance = distance
        self.people = {}

    def check_person(self, person_id, x, y, current_time):
        if person_id not in self.people:
            self.people[person_id] = {
                "x": x,
                "y": y,
                "start": current_time
            }
            return False

        person = self.people[person_id]

        movement = (
            (x - person["x"]) ** 2 +
            (y - person["y"]) ** 2
        ) ** 0.5

        if movement > self.distance:
            person["start"] = current_time

        person["x"] = x
        person["y"] = y

        elapsed = current_time - person["start"]
        return elapsed >= self.threshold