class BaseVitreaModel:
    pass

class FloorModel(BaseVitreaModel):
    def __init__(self, id, name):
        self.id = id
        self.name = name
        self.rooms = set()

    def add_room(self, room):
        self.rooms.add(room)

    def serialize(self, incl_relations=False):
        result = {
            "id": self.id,
            "name": self.name
        }
        if incl_relations:
            result["rooms"] = [room.serialize() for room in self.rooms]
        else:
            result["room_ids"] = [room.id for room in self.rooms]
        return result
        

class RoomModel(BaseVitreaModel):
    def __init__(self, id, name, floor_id):
        self.id = id
        self.name = name
        self.floor_id = floor_id
        self.floor = None
        self.keys = set()
        self.air_conditioners = set()
        self.scenarios = set()

    def set_floor(self, floor):
        self.floor = floor

    def add_key(self, key):
        self.keys.add(key)

    def add_air_conditioner(self, air_conditioner):
        self.air_conditioners.add(air_conditioner)

    def add_scenario(self, scenario):
        self.scenarios.add(scenario)

    def serialize(self, incl_relations=False):
        result = {
            "id": self.id,
            "name": self.name,
            "floor": self.floor.serialize()
        }
        if incl_relations:
            result["keys"] = [key.serialize() for key in self.keys]
            result["air_conditioners"] = [ac.serialize() for ac in self.air_conditioners]
            result["scenarios"] = [scenario.serialize() for scenario in self.scenarios]
        else:
            result["key_ids"] = [f"N{key.keypad_id:03d}-{key.id}" for key in self.keys]
            result["ac_ids"] = [ac.id for ac in self.air_conditioners]
            result["scenario_ids"] = [scenario.id for scenario in self.scenarios]
        return result

class KeypadModel(BaseVitreaModel):
    def __init__(self, id):
        self.id = id
        self.keys = set()

    def add_key(self, key):
        self.keys.add(key)
    
    def serialize(self, incl_relations=False):
        result = {"id": self.id}
        if incl_relations:
            result["keys"] = [key.serialize() for key in self.keys]
        else:
            result["key_ids"] = [f"N{key.keypad_id:03d}-{key.id}" for key in self.keys]
        return result

class KeyModel(BaseVitreaModel):
    def __init__(self, id, name, type, keypad_id, room_id):
        self.id = id
        self.name = name
        self.type = type
        self.keypad_id = keypad_id
        self.keypad = None
        self.room_id = room_id
        self.room = None

    def set_room(self, room):
        self.room = room

    def set_keypad(self, keypad):
        self.keypad = keypad
    
    def serialize(self, incl_relations=False):
        key = {
            "id": self.id,
            "name": self.name,
            "type": {
                "name": self.type.name,
                "value": self.type.value
            },
            "keypad_id": self.keypad_id
        }
        if incl_relations:
            key["room"] = self.room.serialize()
        else:
            key["room_id"] = self.room_id
        return key

class AirConditionerModel(BaseVitreaModel):
    def __init__(self, id, name, type, room_id):
        self.id = id
        self.name = name
        self.type = type
        self.room_id = room_id
        self.room = None

    def set_room(self, room):
        self.room = room
    
    def serialize(self, incl_relations=False):
        result = {
            "id": self.id,
            "name": self.name,
            "type": {
                "name": self.type.name,
                "value": self.type.value
            }
        }
        if incl_relations:
            result["room"] = self.room.serialize()
        else:
            result["room_id"] = self.room_id
        return result

class ScenarioModel(BaseVitreaModel):
    def __init__(self, id, name, room_id):
        self.id = id
        self.name = name
        self.room_id = room_id
        self.room = None
    
    def set_room(self, room):
        self.room = room
    
    def serialize(self, incl_relations=False):
        result = {
            "id": self.id,
            "name": self.name
        }
        if self.room:
            if incl_relations:
                result["room"] = self.room.serialize()
            else:
                result["room_id"] = self.room_id
        else:
            if incl_relations:
                result["room"] = None
            else:
                result["room_id"] = None
        return result

class VitreaDatabaseModel:
    def __init__(self):
        self.floors = set()
        self.rooms = set()
        self.keypads = set()
        self.keys = set()
        self.air_conditioners = set()
        self.scenarios = set()
        self.no_of_floors = 999
        self.no_of_rooms = 999
        self.no_of_keys = 999
        self.no_of_acs = 999
        self.no_of_scenarios = 999
        self._relationships_resolved = False
        self.serialized_data = None

    def is_floors_loaded(self) -> bool:
        return len(self.floors) == self.no_of_floors
    
    def is_rooms_loaded(self) -> bool:
        return len(self.rooms) == self.no_of_rooms

    def is_keys_loaded(self) -> bool:
        return len(self.keys) == self.no_of_keys
    
    def is_acs_loaded(self) -> bool:
        return len(self.air_conditioners) == self.no_of_acs
    
    def is_scenarios_loaded(self) -> bool:
        return len(self.scenarios) == self.no_of_scenarios

    def is_loaded(self) -> bool:
        return all([
            self.is_floors_loaded(),
            self.is_rooms_loaded(),
            self.is_keys_loaded(),
            self.is_acs_loaded(),
            self.is_scenarios_loaded()
        ])

    def add_floor(self, floor):
        self.floors.add(floor)

    def add_room(self, room):
        self.rooms.add(room)

    def add_keypad(self, keypad):
        self.keypads.add(keypad)

    def add_key(self, key):
        self.keys.add(key)

    def add_air_conditioner(self, air_conditioner):
        self.air_conditioners.add(air_conditioner)

    def add_scenario(self, scenario):
        self.scenarios.add(scenario)

    def add_object(self, obj:BaseVitreaModel):
        if not isinstance(obj, BaseVitreaModel):
            raise ValueError("Object must be an instance of BaseVitreaModel")
        if isinstance(obj, FloorModel):
            self.add_floor(obj)
        elif isinstance(obj, RoomModel):
            self.add_room(obj)
        elif isinstance(obj, KeypadModel):
            self.add_keypad(obj)
        elif isinstance(obj, KeyModel):
            self.add_key(obj)
        elif isinstance(obj, AirConditionerModel):
            self.add_air_conditioner(obj)
        elif isinstance(obj, ScenarioModel):
            self.add_scenario(obj)

    def _resolve_relationships(self, force_refresh=False):
        if not self.is_loaded():
            raise ValueError("Database is not fully loaded")
        if self._relationships_resolved and not force_refresh:
            return
        # Resolve Room to Floor relationship
        for room in self.rooms:
            # Assume `room.floor` initially contains floor_id
            floor = next((f for f in self.floors if f.id == room.floor_id), None)
            if floor:
                room.floor = floor
                floor.add_room(room)  # Ensuring bidirectional consistency
        for key in self.keys:
            keypad = next((k for k in self.keypads if k.id == key.keypad_id), None)
            if keypad:
                key.set_keypad(keypad)
                keypad.add_key(key)
            room = next((r for r in self.rooms if r.id == key.room_id), None)
            if room:
                key.set_room(room)
                room.add_key(key)
        for ac in self.air_conditioners:
            room = next((r for r in self.rooms if r.id == ac.room_id), None)
            if room:
                ac.set_room(room)
                room.add_air_conditioner(ac)
        for scenario in self.scenarios:
            if not scenario.room_id:
                continue
            room = next((r for r in self.rooms if r.id == scenario.room_id), None)
            if room:
                scenario.set_room(room)
                room.add_scenario(scenario)
        self._relationships_resolved = True
    
    def serialize(self, force_refresh=False):
        if not self.serialized_data or force_refresh:
            if not self.is_loaded():
                raise ValueError("Database is not fully loaded")
            self._resolve_relationships(force_refresh)
            self.serialized_data = {
                "floors": [floor.serialize(incl_relations=True) for floor in self.floors],
                "rooms": [room.serialize(incl_relations=True) for room in self.rooms],
                "keypads": [keypad.serialize(incl_relations=True) for keypad in self.keypads],
                "keys": [key.serialize(incl_relations=True) for key in self.keys],
                "air_conditioners": [ac.serialize(incl_relations=True) for ac in self.air_conditioners],
                "scenarios": [scenario.serialize(incl_relations=True) for scenario in self.scenarios]
            }
        return self.serialized_data 
    
    def serialize_partial(self):
        self._resolve_relationships()
        return {
            "floors": [floor.serialize() for floor in self.floors],
            "rooms": [room.serialize() for room in self.rooms],
            "keypads": [keypad.serialize() for keypad in self.keypads],
            "keys": [key.serialize() for key in self.keys],
            "air_conditioners": [ac.serialize() for ac in self.air_conditioners],
            "scenarios": [scenario.serialize() for scenario in self.scenarios]
        }
    
    def serialize_floors(self):
        self._resolve_relationships()
        if self.serialized_data:
            return self.serialized_data["floors"]
        return [floor.serialize(incl_relations=True) for floor in self.floors]
    
    def serialize_rooms(self):
        self._resolve_relationships()
        if self.serialized_data:
            return self.serialized_data["rooms"]
        return [room.serialize(incl_relations=True) for room in self.rooms]
    
    def serialize_keypads(self):
        self._resolve_relationships()
        if self.serialized_data:
            return self.serialized_data["keypads"]
        return [keypad.serialize(incl_relations=True) for keypad in self.keypads]
    
    def serialize_keys(self):
        self._resolve_relationships()
        if self.serialized_data:
            return self.serialized_data["keys"]
        return [key.serialize(incl_relations=True) for key in self.keys]
    
    def serialize_air_conditioners(self):
        self._resolve_relationships()
        if self.serialized_data:
            return self.serialized_data["air_conditioners"]
        return [ac.serialize(incl_relations=True) for ac in self.air_conditioners]
    
    def serialize_scenarios(self):
        self._resolve_relationships()
        if self.serialized_data:
            return self.serialized_data["scenarios"]
        return [scenario.serialize(incl_relations=True) for scenario in self.scenarios]
    