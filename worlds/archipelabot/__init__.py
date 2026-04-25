import sys
from pathlib import Path

vendor_path = str(Path(__file__).resolve().parent / "vendor")
if vendor_path not in sys.path:
    sys.path.insert(0, vendor_path)

from worlds.LauncherComponents import Component, components, Type, launch as launch_component, launch_subprocess
from worlds.AutoWorld import World
from Options import PerGameCommonOptions

class ArchipelaBotWorld(World):
    """
    ArchipelaBot is a Discord bot for monitoring and controlling Archipelago Multiworld sessions.
    """
    game = "ArchipelaBot"
    options_dataclass = PerGameCommonOptions
    item_name_to_id = {}
    location_name_to_id = {}

    def create_regions(self):
        # No regions needed
        pass

    def create_items(self):
        # No items needed
        pass

def start_client() -> None:
    from .Client import launch
    launch_subprocess(launch, name="ArchipelaBot")

component = Component("ArchipelaBot", component_type=Type.CLIENT, func=start_client)
components.append(component)