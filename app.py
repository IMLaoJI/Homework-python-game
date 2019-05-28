"""
Simple 2d world where the player can interact with the items in the world.
"""

__author__ = ""
__date__ = ""
__version__ = "1.1.0"
__copyright__ = "The University of Queensland, 2019"

import tkinter as tk
from tkinter import messagebox
import random
from collections import namedtuple

import pymunk

from block import Block, ResourceBlock, BREAK_TABLES, LeafBlock, TrickCandleFlameBlock
from grid import Stack, Grid, SelectableGrid, ItemGridView
from item import Item, SimpleItem, HandItem, BlockItem, MATERIAL_TOOL_TYPES, TOOL_DURABILITIES
from player import Player
from dropped_item import DroppedItem
from crafting import GridCrafter, CraftingWindow
from world import World
from core import positions_in_range
from game import GameView, WorldViewRouter
from mob import Bird

BLOCK_SIZE = 2 ** 5
GRID_WIDTH = 2 ** 5
GRID_HEIGHT = 2 ** 4

# Task 3/Post-grad only:
# Class to hold game data that is passed to each thing's step function
# Normally, this class would be defined in a separate file
# so that type hinting could be used on PhysicalThing & its
# subclasses, but since it will likely need to be extended
# for these tasks, we have defined it here
GameData = namedtuple('GameData', ['world', 'player'])


def create_block(*block_id):
    """(Block) Creates a block (this function can be thought of as a block factory)

    Parameters:
        block_id (*tuple): N-length tuple to uniquely identify the block,
        often comprised of strings, but not necessarily (arguments are grouped
        into a single tuple)

    Examples:
        >>> create_block("leaf")
        LeafBlock()
        >>> create_block("stone")
        ResourceBlock('stone')
        >>> create_block("mayhem", 1)
        TrickCandleFlameBlock(1)
    """
    if len(block_id) == 1:
        block_id = block_id[0]
        if block_id == "leaf":
            return LeafBlock()
        elif block_id in BREAK_TABLES:
            return ResourceBlock(block_id, BREAK_TABLES[block_id])

    elif block_id[0] == 'mayhem':
        return TrickCandleFlameBlock(block_id[1])

    raise KeyError(f"No block defined for {block_id}")


def create_item(*item_id):
    """(Item) Creates an item (this function can be thought of as a item factory)

    Parameters:
        item_id (*tuple): N-length tuple to uniquely identify the item,
        often comprised of strings, but not necessarily (arguments are grouped
        into a single tuple)

    Examples:
        >>> create_item("dirt")
        BlockItem('dirt')
        >>> create_item("hands")
        HandItem('hands')
        >>> create_item("pickaxe", "stone")  # *without* Task 2.1.2 implemented
        Traceback (most recent call last):
        ...
        NotImplementedError: "Tool creation is not yet handled"
        >>> create_item("pickaxe", "stone")  # *with* Task 2.1.2 implemented
        ToolItem('stone_pickaxe')
    """
    if len(item_id) == 2:

        if item_id[0] in MATERIAL_TOOL_TYPES and item_id[1] in TOOL_DURABILITIES:
            raise NotImplementedError("Tool creation is not yet handled")

    elif len(item_id) == 1:

        item_type = item_id[0]

        if item_type == "hands":
            return HandItem("hands")

        elif item_type == "dirt":
            return BlockItem(item_type)

        # Task 1.4 Basic Items: Create wood & stone here
        elif item_type == "wood" or item_type == "stone":
            return BlockItem(item_type)

        elif item_type == "apple":
            return FoodItem(item_type, 2)

        elif item_type == "crafting_table":
            return BlockItem(item_type)

        elif item_type == "stick":
            return SimpleItem(item_type)

    raise KeyError(f"No item defined for {item_id}")


class FoodItem(Item):

    def __init__(self, item_id: str, strength: float):
        super(FoodItem, self).__init__(item_id)
        self._strength = strength

    def get_strength(self):
        return self._strength

    def can_attack(self) -> bool:
        return False

    def place(self):
        return [('effect', ('food', self._strength))]

    def get_durability(self):
        pass

    def get_max_durability(self):
        pass

    def attack(self, successful):
        pass


class ToolItem(Item):

    def __init__(self, item_id: str, tool_type: str, durability: float):
        super(ToolItem, self).__init__(item_id)
        self._tool_type = tool_type
        self._durability = durability

    def get_type(self):
        return self._tool_type

    def can_attack(self) -> bool:
        if self._durability > 0:
            return True
        return False

    def place(self):
        pass

    def get_durability(self):
        return self._durability

    def get_max_durability(self):
        for tool, duration in TOOL_DURABILITIES:
            if tool == self._tool_type:
                return duration

    def attack(self, successful):
        if successful:
            return True
        else:
            self._durability -= 1


class CraftingTableBlock(ResourceBlock):
    # ResourceBlock(block_id, BREAK_TABLES[block_id])

    def __init__(self, block_id, break_table):
        super(CraftingTableBlock, self).__init__(block_id, break_table)
        self._block_id = block_id
        self._break_table = break_table
        print(block_id, break_table)

    def get_drops(self, luck, correct_item_used):
        if correct_item_used:
            return [('item', ('crafting_table',))]

    def use(self):
        return 'crafting', 'crafting_table'


# Task 1.3: Implement StatusView class here
class StatusView(tk.Frame):
    def __init__(self, master, player):
        super().__init__(master)
        self.pack()
        self.player = player
        self.health = tk.StringVar()
        self.food = tk.StringVar()
        self.health_image = tk.PhotoImage(file='images/health.gif')
        self.food_image = tk.PhotoImage(file='images/food.gif')
        self.label_image1 = tk.Label(self, image=self.health_image).pack(side=tk.LEFT)
        self.label_text1 = tk.Label(self, textvariable=self.health).pack(side=tk.LEFT)
        self.label_image2 = tk.Label(self, image=self.food_image).pack(side=tk.LEFT)
        self.label_text2 = tk.Label(self, textvariable=self.food).pack(side=tk.RIGHT)
        self.show_status()

    def show_status(self):
        self.health.set('Health:' + str(float(self.player.get_health())))
        self.food.set('Food:' + str(float(self.player.get_food())))


BLOCK_COLOURS = {
    'diamond': 'blue',
    'dirt': '#552015',
    'stone': 'grey',
    'wood': '#723f1c',
    'leaves': 'green',
    'crafting_table': 'pink',
    'furnace': 'black',
}

ITEM_COLOURS = {
    'diamond': 'blue',
    'dirt': '#552015',
    'stone': 'grey',
    'wood': '#723f1c',
    'apple': '#ff0000',
    'leaves': 'green',
    'crafting_table': 'pink',
    'furnace': 'black',
    'cooked_apple': 'red4'
}

CRAFTING_RECIPES_2x2 = [
    (
        (
            ('wood', 'wood'),
            ('wood', 'wood')
        ),
        Stack(create_item('wood'), 10)
    )
]

CRAFTING_RECIPES_3x3 = {
    (
        (
            (None, None, None),
            (None, 'wood', None),
            (None, 'wood', None)
        ),
        Stack(create_item('wood'), 16)
    )
}

# CRAFTING_RECIPES_2x2 = [
#     ...
#     (
#         (
#             ('wood', 'wood'),
#             ('wood', 'wood')
#         ),
#         Stack(create_item('crafting_table'), 1)
#     ),
#     ...
# ]

# CRAFTING_RECIPES_3x3 = {
#     (
#         (
#             (None, None, None),
#             (None, 'wood', None),
#             (None, 'wood', None)
#         ),
#         Stack(create_item('stick'), 16)
#     ),
#     (
#         (
#             ('wood', 'wood', 'wood'),
#             (None, 'stick', None),
#             (None, 'stick', None)
#         ),
#         Stack(create_item('pickaxe', 'wood'), 1)
#     ),
#     (
#         (
#             ('wood', 'wood', None),
#             ('wood', 'stick', None),
#             (None, 'stick', None)
#         ),
#         Stack(create_item('axe', 'wood'), 1)
#     ),
#     (
#         (
#             (None, 'wood', None),
#             (None, 'stick', None),
#             (None, 'stick', None)
#         ),
#         Stack(create_item('shovel', 'wood'), 1)
#     ),
#     (
#         (
#             (None, 'stone', None),
#             (None, 'stone', None),
#             (None, 'stick', None)
#         ),
#         Stack(create_item('sword', 'wood'), 1)
#     )
# }


def load_simple_world(world):
    """Loads blocks into a world

    Parameters:
        world (World): The game world to load with blocks
    """
    block_weights = [
        (100, 'dirt'),
        (30, 'stone'),
    ]

    cells = {}

    ground = []

    width, height = world.get_grid_size()

    for x in range(width):
        for y in range(height):
            if x < 22:
                if y <= 8:
                    continue
            else:
                if x + y < 30:
                    continue

            ground.append((x, y))

    weights, blocks = zip(*block_weights)
    kinds = random.choices(blocks, weights=weights, k=len(ground))

    for cell, block_id in zip(ground, kinds):
        cells[cell] = create_block(block_id)

    trunks = [(3, 8), (3, 7), (3, 6), (3, 5)]

    for trunk in trunks:
        cells[trunk] = create_block('wood')

    leaves = [(4, 3), (3, 3), (2, 3), (4, 2), (3, 2), (2, 2), (4, 4), (3, 4), (2, 4)]

    for leaf in leaves:
        cells[leaf] = create_block('leaf')

    for cell, block in cells.items():
        # cell -> box
        i, j = cell

        world.add_block_to_grid(block, i, j)

    world.add_block_to_grid(create_block("mayhem", 0), 14, 8)

    world.add_mob(Bird("friendly_bird", (12, 12)), 400, 100)


class MyMenu:

    def __init__(self, root):
        self._root = root

        self.menubar = tk.Menu(root)

        filemenu = tk.Menu(self.menubar, tearoff=0)
        filemenu.add_command(label="New Game", command=self.new_game)
        filemenu.add_command(label="Exit", command=self.quit_game)

        self.menubar.add_cascade(label="File", menu=filemenu)

        root.config(menu=self.menubar)

    def new_game(self):
        ans = messagebox.askokcancel("New Game", "Start a new game?")
        if ans:
            self._root.destroy()
            main()

    def quit_game(self):
        ans = messagebox.askokcancel("Exit", "Do you want to exit?")
        if ans:
            self._root.destroy()


class Ninedraft:
    """High-level app class for Ninedraft, a 2d sandbox game"""

    def __init__(self, master):
        """Constructor

        Parameters:
            master (tk.Tk): tkinter root widget
        """

        self._master = master
        self._world = World((GRID_WIDTH, GRID_HEIGHT), BLOCK_SIZE)

        load_simple_world(self._world)

        self._player = Player()
        self._world.add_player(self._player, 250, 150)

        self._world.add_collision_handler("player", "item", on_begin=self._handle_player_collide_item)

        self._hot_bar = SelectableGrid(rows=1, columns=10)
        self._hot_bar.select((0, 0))

        starting_hotbar = [
            Stack(create_item("dirt"), 20),
            Stack(create_item("apple"), 4)
        ]

        for i, item in enumerate(starting_hotbar):
            self._hot_bar[0, i] = item

        self._hands = create_item('hands')

        starting_inventory = [
            ((1, 5), Stack(Item('dirt'), 10)),
            ((0, 2), Stack(Item('wood'), 10)),
        ]
        self._inventory = Grid(rows=3, columns=10)
        for position, stack in starting_inventory:
            self._inventory[position] = stack

        self._crafting_window = None
        self._master.bind("e",
                          lambda e: self.run_effect(('crafting', 'basic')))

        self._view = GameView(master, self._world.get_pixel_size(), WorldViewRouter(BLOCK_COLOURS, ITEM_COLOURS))
        self._view.pack()

        # Task 1.2 Mouse Controls: Bind mouse events here
        self._view.bind("<Motion>", lambda e: self._mouse_move(e))
        self._view.bind("<Button-1>", lambda e: self._left_click(e))
        self._view.bind("<Button-3>", lambda e: self._right_click(e))

        # Task 1.3: Create instance of StatusView here
        self._status = StatusView(master, self._player)

        self._hot_bar_view = ItemGridView(master, self._hot_bar.get_size())
        self._hot_bar_view.pack(side=tk.TOP, fill=tk.X)

        # Task 1.5 Keyboard Controls: Bind to space bar for jumping here
        self._master.bind("<space>", lambda e: self._jump())

        self._master.bind("a", lambda e: self._move(-1, 0))
        self._master.bind("<Left>", lambda e: self._move(-1, 0))
        self._master.bind("d", lambda e: self._move(1, 0))
        self._master.bind("<Right>", lambda e: self._move(1, 0))
        self._master.bind("s", lambda e: self._move(0, 1))
        self._master.bind("<Down>", lambda e: self._move(0, 1))

        # Task 1.5 Keyboard Controls: Bind numbers to hotbar activation here
        for i in range(0, 10):
            self._master.bind(i, lambda e: self._select_hot_bar(e))

        # Task 1.6 File Menu & Dialogs: Add file menu here
        self._menu = MyMenu(master)

        self._target_in_range = False
        self._target_position = 0, 0

        self.redraw()

        self.step()

    def redraw(self):
        self._view.delete(tk.ALL)

        # physical things
        self._view.draw_physical(self._world.get_all_things())

        # target
        target_x, target_y = self._target_position
        target = self._world.get_block(target_x, target_y)
        cursor_position = self._world.grid_to_xy_centre(*self._world.xy_to_grid(target_x, target_y))

        # Task 1.2 Mouse Controls: Show/hide target here
        if self._target_in_range:
            self._view.show_target(self._player.get_position(), cursor_position)
        else:
            self._view.hide_target()

        # Task 1.3 StatusView: Update StatusView values here
        self._status.show_status()

        # hot bar
        self._hot_bar_view.render(self._hot_bar.items(), self._hot_bar.get_selected())

    def step(self):
        data = GameData(self._world, self._player)
        self._world.step(data)
        self.check_target()
        self.redraw()

        # Task 1.6 File Menu & Dialogs: Handle the player's death if necessary
        if data.player.get_health() == 0:
            self._menu.new_game()
            return

        self._master.after(15, self.step)

    def _select_hot_bar(self, event):
        num = int(event.keysym)
        if num == 0:
            num = 9
        else:
            num -= 1
        selected = self._hot_bar.get_selected()
        if selected is None:
            self._hot_bar.select((0, num))
        elif selected[1] == num:
            self._hot_bar.deselect()
        else:
            self._hot_bar.select((0, num))

    def _move(self, dx, dy):
        velocity = self._player.get_velocity()
        self._player.set_velocity((velocity.x + dx * 80, velocity.y + dy * 80))

    def _jump(self):
        velocity = self._player.get_velocity()
        # Task 1.2: Update the player's velocity here
        self._player.set_velocity((velocity.x, velocity.y - 160))

    def mine_block(self, block, x, y):
        luck = random.random()

        active_item, effective_item = self.get_holding()

        was_item_suitable, was_attack_successful = block.mine(effective_item, active_item, luck)

        effective_item.attack(was_attack_successful)

        if block.is_mined():
            # Task 1.2 Mouse Controls: Reduce the player's food/health appropriately
            if self._player.get_food() > 0:
                self._player.change_food(-0.5)
            elif self._player.get_health() > 0:
                self._player.change_health(-0.5)

            # Task 1.2 Mouse Controls: Remove the block from the world & get its drops
            self._world.remove_block(block)
            drops = block.get_drops(luck, was_item_suitable)

            if not drops:
                return

            x0, y0 = block.get_position()

            for i, (drop_category, drop_types) in enumerate(drops):
                print(f'Dropped {drop_category}, {drop_types}')

                if drop_category == "item":
                    physical = DroppedItem(create_item(*drop_types))

                    # this is so bleh
                    x = x0 - BLOCK_SIZE // 2 + 5 + (i % 3) * 11 + random.randint(0, 2)
                    y = y0 - BLOCK_SIZE // 2 + 5 + ((i // 3) % 3) * 11 + random.randint(0, 2)

                    self._world.add_item(physical, x, y)
                elif drop_category == "block":
                    self._world.add_block(create_block(*drop_types), x, y)
                else:
                    raise KeyError(f"Unknown drop category {drop_category}")

    def get_holding(self):
        active_stack = self._hot_bar.get_selected_value()
        active_item = active_stack.get_item() if active_stack else self._hands

        effective_item = active_item if active_item.can_attack() else self._hands

        return active_item, effective_item

    def check_target(self):
        # select target block, if possible
        active_item, effective_item = self.get_holding()

        pixel_range = active_item.get_attack_range() * self._world.get_cell_expanse()

        self._target_in_range = positions_in_range(self._player.get_position(),
                                                   self._target_position,
                                                   pixel_range)

    def _mouse_move(self, event):
        self._target_position = event.x, event.y
        self.check_target()

    def _left_click(self, event):
        # Invariant: (event.x, event.y) == self._target_position
        #  => Due to mouse move setting target position to cursor
        x, y = self._target_position

        if self._target_in_range:
            block = self._world.get_block(x, y)
            if block:
                self.mine_block(block, x, y)

    def _trigger_crafting(self, craft_type):
        print(f"Crafting with {craft_type}")
        crafter = GridCrafter(CRAFTING_RECIPES_2x2)
        craft_window = CraftingWindow(self._master, 'CraftingWindow', self._hot_bar, self._inventory, crafter)

    def run_effect(self, effect):
        if len(effect) == 2:
            if effect[0] == "crafting":
                craft_type = effect[1]

                if craft_type == "basic":
                    print("Can't craft much on a 2x2 grid :/")

                elif craft_type == "crafting_table":
                    print("Let's get our kraft® on! King of the brands")

                self._trigger_crafting(craft_type)
                return
            elif effect[0] in ("food", "health"):
                stat, strength = effect
                print(f"Gaining {strength} {stat}!")
                getattr(self._player, f"change_{stat}")(strength)
                return

        raise KeyError(f"No effect defined for {effect}")

    def _right_click(self, event):

        x, y = self._target_position
        target = self._world.get_thing(x, y)

        if target:
            # use this thing
            print(f'using {target}')
            effect = target.use()
            print(f'used {target} and got {effect}')

            if effect:
                self.run_effect(effect)

        else:
            # place active item
            selected = self._hot_bar.get_selected()

            if not selected:
                return

            stack = self._hot_bar[selected]
            drops = stack.get_item().place()

            stack.subtract(1)
            if stack.get_quantity() == 0:
                # remove from hotbar
                self._hot_bar[selected] = None

            if not drops:
                return

            # handling multiple drops would be somewhat finicky, so prevent it
            if len(drops) > 1:
                raise NotImplementedError("Cannot handle dropping more than 1 thing")

            drop_category, drop_types = drops[0]

            x, y = event.x, event.y

            if drop_category == "block":
                existing_block = self._world.get_block(x, y)

                if not existing_block:
                    self._world.add_block(create_block(drop_types[0]), x, y)
                else:
                    raise NotImplementedError(
                        "Automatically placing a block nearby if the target cell is full is not yet implemented")

            elif drop_category == "effect":
                self.run_effect(drop_types)

            else:
                raise KeyError(f"Unknown drop category {drop_category}")

    def _activate_item(self, index):
        print(f"Activating {index}")

        self._hot_bar.toggle_selection((0, index))

    def _handle_player_collide_item(self, player: Player, dropped_item: DroppedItem, data,
                                    arbiter: pymunk.Arbiter):
        """Callback to handle collision between the player and a (dropped) item. If the player has sufficient space in
        their to pick up the item, the item will be removed from the game world.

        Parameters:
            player (Player): The player that was involved in the collision
            dropped_item (DroppedItem): The (dropped) item that the player collided with
            data (dict): data that was added with this collision handler (see data parameter in
                         World.add_collision_handler)
            arbiter (pymunk.Arbiter): Data about a collision
                                      (see http://www.pymunk.org/en/latest/pymunk.html#pymunk.Arbiter)
                                      NOTE: you probably won't need this
        Return:
             bool: False (always ignore this type of collision)
                   (more generally, collision callbacks return True iff the collision should be considered valid; i.e.
                   returning False makes the world ignore the collision)
        """

        item = dropped_item.get_item()

        if self._hot_bar.add_item(item):
            print(f"Added 1 {item!r} to the hotbar")
        elif self._inventory.add_item(item):
            print(f"Added 1 {item!r} to the inventory")
        else:
            print(f"Found 1 {item!r}, but both hotbar & inventory are full")
            return True

        self._world.remove_item(dropped_item)
        return False


# Task 1.1 App class: Add a main function to instantiate the GUI here
def main():
    root = tk.Tk()
    root.title('Ninedraft')
    app = Ninedraft(root)
    root.mainloop()


if __name__ == '__main__':
    main()
