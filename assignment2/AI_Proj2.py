from random import randint, uniform, choice
from matplotlib import pyplot
from math import e as exp
from inspect import currentframe
from time import time
from multiprocessing import Process, Queue, cpu_count

#Constants
CLOSED_CELL = 1
OPEN_CELL = 2
BOT_CELL = 4
CREW_CELL = 8
ALIEN_CELL = 16
BOT_CAUGHT_CELL = 32
BOT_MOVEMENT_CELLS = OPEN_CELL | CREW_CELL | ALIEN_CELL
ALIEN_MOVEMENT_CELLS = CREW_CELL | OPEN_CELL # | BOT_CELL
GRID_SIZE = 3

X_COORDINATE_SHIFT = [1, 0, 0, -1]
Y_COORDINATE_SHIFT = [0, 1, -1, 0]

ALIEN_ZONE_SIZE = 0 # k - k >= 1, need to determine the large value
ALPHA = 0.2 # avoid alpha > 11 for 35x35
IDLE_BEEP_COUNT = 10

TOTAL_ITERATIONS = 1000
MAX_ALPHA_ITERATIONS = 10
ALPHA_STEP_INCREASE = 0.2
TOTAL_BOTS = 2

LOG_NONE = 0
LOG_DEBUG_ALIEN = 0.5
LOG_INFO = 1
LOG_DEBUG = 2
LOG_DEBUG_GRID = 3
IGNORE_GRID_DEBUG = True

LOOKUP_E = []
LOOKUP_NOT_E = []

ALIEN_NOT_PRESENT = 0
ALIEN_PRESENT = 1


# Common Methods
def get_neighbors(size, cell, grid, filter):
    neighbors = []

    for i in range(4):
        x_cord = cell[0] + X_COORDINATE_SHIFT[i]
        y_cord = cell[1] + Y_COORDINATE_SHIFT[i]
        if (
            (0 <= x_cord < size)
            and (0 <= y_cord < size)
            and (grid[x_cord][y_cord].cell_type & filter)
        ):
            neighbors.append((x_cord, y_cord))

    return neighbors

def get_manhattan_distance(cell_1, cell_2):
    return abs(cell_1[0] - cell_2[0]) + abs(cell_1[1] - cell_2[1])

def check_for_failure(bot, condition):
    if condition == 1 and (len(bot.crew_search_data.crew_cells) == 0):
        print(currentframe().f_back.f_code.co_name, "::", currentframe().f_back.f_lineno)
        bot.logger.print(LOG_NONE, f"curr pos {bot.curr_pos}, crew_1 {bot.ship.crew_1}, crew_2 {bot.ship.crew_2}")
        bot.logger.print(LOG_NONE, f"No crew cells!!!")
        bot.logger.print(LOG_NONE, f"pred_crew_cells::{bot.pred_crew_cells}")
        bot.logger.print(LOG_NONE, f"path_traversed::{bot.path_traversed}")
        exit()
    elif condition == 2 and not bot.crew_search_data.beep_prob: # some serious issue
        print(currentframe().f_back.f_code.co_name, "::", currentframe().f_back.f_lineno)
        val = 0.0
        for cell_cord in bot.crew_search_data.crew_cells:
            cell = bot.ship.get_cell(cell_cord)
            val += cell.crew_probs.crew_and_beep
            bot.logger.print_cell_data(LOG_NONE, cell.crew_probs, cell.cord, bot.curr_pos)
        bot.logger.print(LOG_NONE, f"{bot.crew_search_data.beep_prob}, {val}")
        bot.logger.print(LOG_NONE, f"is_beep_recv::{bot.crew_search_data.is_beep_recv}, {bot.ship.isBeep}")
        bot.logger.print(LOG_NONE, f"Bot in {bot.curr_pos} has to find crew({bot.total_crew_to_save}) {bot.ship.crew_1, bot.ship.crew_2} with pending crew {bot.pending_crew}")
        bot.logger.print(LOG_NONE, f"path_traversed {bot.path_traversed}")
        bot.logger.print(LOG_NONE, f"The crew cells are {bot.crew_search_data.crew_cells}. The pred cells is {bot.pred_crew_cells}, with traverse path {bot.traverse_path}")
        exit()

# used for debugging (mostly...)
class Logger:
    def __init__(self, log_level):
        self.log_level = log_level

    def check_log_level(self, log_level):
        return (self.log_level >= 0) and (log_level <= self.log_level)

    def print(self, log_level, *args):
        if self.check_log_level(log_level):
            print(currentframe().f_back.f_code.co_name, "::", currentframe().f_back.f_lineno, "::", sep="", end="")
            print(*args)

    def print_cell_data(self, log_level, crew_probs, cords, curr_pos):
        if self.check_log_level(log_level):
            print(currentframe().f_back.f_code.co_name, "::", currentframe().f_back.f_lineno, "::", sep="", end="")
            print(f"curr_pos::{curr_pos}, cell_cord::{(cords.cell_1, cords.cell_2) if type(cords) is Cell_Pair else cords}, cell_distance::{crew_probs.bot_distance}, crew_prob::{crew_probs.crew_prob}, beep_given_crew::{crew_probs.beep_given_crew}, no_beep_given_crew::{crew_probs.no_beep_given_crew}, crew_and_beep::{crew_probs.crew_and_beep}, crew_and_no_beep::{crew_probs.crew_and_no_beep}")

    def print_grid(self, grid, log_level = LOG_DEBUG_GRID):
        # if not self.check_log_level(log_level):
        #     return

        print("****************")
        for i, cells in enumerate(grid):
            for j, cell in enumerate(cells):
                print("%10s" % (str(i) + str(j) + "::" + str(cell.cell_type)), end = " ")
            print("")
        print("****************")

    def print_crew_probs(self, grid, is_beep_recv, curr_pos):
        # if IGNORE_GRID_DEBUG and not self.check_log_level(LOG_DEBUG_GRID):
        return

        prob_grid = []
        prob_spread = list()
        for cells in grid:
            prob_cell = []
            for cell in cells:
                if cell.cell_type == CLOSED_CELL:
                    prob_cell.append(float('nan'))
                elif cell.cell_type == (BOT_CELL|CREW_CELL):
                    prob_cell.append(1)
                else:
                    prob_cell.append(cell.crew_probs.crew_prob)
                    if not cell.crew_probs.crew_prob in prob_spread:
                        prob_spread.append(cell.crew_probs.crew_prob)
            prob_grid.append(prob_cell)

        prob_spread.sort()
        max_len = len(prob_spread) - 1
        prob_grid[curr_pos[0]][curr_pos[1]] = prob_spread[max_len]

        pyplot.figure(figsize=(10,10))
        pyplot.colorbar(pyplot.imshow(prob_grid, vmin=prob_spread[0], vmax=prob_spread[max_len]))
        pyplot.title("Beep recv" if is_beep_recv else "Beep not recv")
        pyplot.show()


# Modularizing our knowledge base for readbility
class Crew_Probs: # contains all the prob of crew in each cell
    def __init__(self):
        self.bot_distance = 0.0 # distance of curr cell to bot
        self.crew_prob = 0.0 # p(c)
        self.beep_given_crew = 0.0 # p(b|c)
        self.no_beep_given_crew = 0.0 # p(¬b|c)
        self.crew_given_beep = 0.0 # p(c|b)
        self.crew_given_no_beep = 0.0 # p(c|¬b)
        self.crew_and_beep = 0.0 # p (c,b)
        self.crew_and_no_beep = 0.0 # p(c,¬b)
        self.track_beep = list((0, 0))

    def update_crew_probs(self, crew_search_data):
        self.crew_given_beep = (self.crew_and_beep) / crew_search_data.beep_prob
        if (crew_search_data.no_beep_prob != 0):
            self.crew_given_no_beep = (self.crew_and_no_beep) / crew_search_data.no_beep_prob

        self.crew_prob = self.crew_given_beep if crew_search_data.is_beep_recv else self.crew_given_no_beep
        self.crew_and_beep = self.beep_given_crew * self.crew_prob
        self.crew_and_no_beep = self.no_beep_given_crew * self.crew_prob

class Beep:
    def __init__(self):
        self.crew_1_dist = self.crew_2_dist = 0 # distance of current cell to crew
        self.c1_beep_prob = self.c2_beep_prob = 0 # probability of hearing the crews beep from this cell

class Cell: # contains the detail inside each cell (i, j)
    def __init__(self, row, col, cell_type = OPEN_CELL):
        self.cell_type = cell_type # static constant
        self.within_detection_zone = False
        self.crew_probs = Crew_Probs()
        self.alien_probs = Alien_Probs()
        self.listen_beep = Beep()
        self.cord = (row, col) # coordinate of this cell

class Cell_Pair:
    def __init__(self, cell_1, cell_2, ship):
        self.cell_1 = ship.get_cell(cell_1)
        self.cell_2 = ship.get_cell(cell_2)
        self.crew_probs = Crew_Probs()

class Alien_Evasion_Data:
    def __init__(self, ship):
        self.present_alien_cells = list(ship.initial_alien_cells)
        self.all_alien_cells = list(ship.open_cells)
        self.all_alien_cells.extend([ship.crew_1, ship.bot])
        self.is_beep_recv = False

class Crew_Search_Data:
    def __init__(self):
        self.beep_prob = 0.0 # p(b) -> normalized for hearing beeps
        self.no_beep_prob = 0.0 # p(¬b) -> normalized for hearing no beeps
        self.beep_count = 0
        self.is_beep_recv = False

    def set_beeps_prob(self, beep_prob = 0.0, no_beep_prob = 0.0):
        self.beep_prob = beep_prob
        self.no_beep_prob = no_beep_prob

class One_Crew_Search_DS(Crew_Search_Data):
    def __init__(self, ship):
        super(One_Crew_Search_DS, self).__init__()
        self.crew_cells = list(ship.open_cells) # list of all possible crew cells
        self.crew_cells.append(ship.crew_1)
        self.crew_cells.append(ship.crew_2)

    def update_cell_mov_vals(self, crew_probs, curr_pos, cell_cord):
        crew_probs.bot_distance = get_manhattan_distance(curr_pos, cell_cord)
        crew_probs.beep_given_crew = LOOKUP_E[crew_probs.bot_distance]
        crew_probs.no_beep_given_crew = LOOKUP_NOT_E[crew_probs.bot_distance]
        crew_probs.crew_and_beep = crew_probs.beep_given_crew * crew_probs.crew_prob
        crew_probs.crew_and_no_beep = crew_probs.no_beep_given_crew * crew_probs.crew_prob
        self.beep_prob += crew_probs.crew_and_beep
        self.no_beep_prob += crew_probs.crew_and_no_beep

    def remove_cell_probs(self, cell, logger, curr_pos):
        if cell.cord not in self.crew_cells:
            return

        self.crew_cells.remove(cell.cord)
        logger.print(LOG_DEBUG, f"Removing current position{curr_pos} from list of probable crew cells{self.crew_cells}")

    def init_crew_calcs(self, ship, curr_pos):
        crew_cell_size = len(self.crew_cells)
        for cell_cord in self.crew_cells:
            cell = ship.get_cell(cell_cord)
            cell.crew_probs.crew_prob = 1/crew_cell_size
            self.update_cell_mov_vals(cell.crew_probs, curr_pos, cell_cord)

class Two_Crew_Search_DS(One_Crew_Search_DS):
    def __init__(self, ship):
        super(Two_Crew_Search_DS, self).__init__(ship)
        self.crew_cells_pair = dict()
        crew_cells_len = len(self.crew_cells)
        self.crew_cells_length = (crew_cells_len * (crew_cells_len + 1)) / 2

    def update_cell_mov_vals(self, crew_probs, curr_pos, cell_cord):
        crew_probs.bot_distance = get_manhattan_distance(curr_pos, cell_cord)
        crew_probs.beep_given_crew = LOOKUP_E[crew_probs.bot_distance]
        crew_probs.no_beep_given_crew = LOOKUP_NOT_E[crew_probs.bot_distance]

    def update_crew_pair(self, cell_pair, curr_pos, pending_crew):
        cell_1 = cell_pair.cell_1.cord
        cell_2 = cell_pair.cell_2.cord
        if pending_crew == 1:
            cell_2 = curr_pos
        elif pending_crew == 2:
            cell_1 = curr_pos

        self.update_cell_mov_vals(cell_pair.cell_1.crew_probs, curr_pos, cell_1)
        self.update_cell_mov_vals(cell_pair.cell_2.crew_probs, curr_pos, cell_2)

    def update_cell_pair_vals(self, cell_pair, curr_pos, pending_crew = 0):
        self.update_crew_pair(cell_pair, curr_pos, pending_crew)
        crew_probs = cell_pair.crew_probs
        crew_probs.beep_given_crew = 1 - cell_pair.cell_1.crew_probs.no_beep_given_crew * cell_pair.cell_2.crew_probs.no_beep_given_crew
        crew_probs.no_beep_given_crew = cell_pair.cell_1.crew_probs.no_beep_given_crew * cell_pair.cell_2.crew_probs.no_beep_given_crew
        crew_probs.crew_and_beep = crew_probs.beep_given_crew * crew_probs.crew_prob
        crew_probs.crew_and_no_beep = crew_probs.no_beep_given_crew * crew_probs.crew_prob
        self.beep_prob += crew_probs.crew_and_beep
        self.no_beep_prob += crew_probs.crew_and_no_beep

    def remove_crew_probs(self, cell_pair):
        cell_pair.crew_probs.crew_prob = 0
        self.beep_prob -= cell_pair.crew_probs.crew_and_beep
        self.no_beep_prob -= cell_pair.crew_probs.crew_and_no_beep
        del cell_pair

    def remove_cell_probs(self, cell, logger, curr_pos):
        print("Entered here...")
        if curr_pos not in self.crew_cells:
            return

        index = self.crew_cells.index(cell)
        print(self.crew_cells, cell)
        self.crew_cells.remove(cell)
        for itr, key in enumerate(self.crew_cells_pair):
            if itr != index:
                print(key, "::", self.crew_cells_pair[key][index - itr - 1].cell_2.cord)
                self.remove_crew_probs(self.crew_cells_pair[key].pop(index - itr - 1))
            else:
                print(key, "::", end = " ")
                for cell_pair in self.crew_cells_pair[key]:
                    print(cell_pair.cell_2.cord, end = " ")
                    self.remove_crew_probs(cell_pair)
                del self.crew_cells_pair[key]
                print()
                break

        logger.print(LOG_DEBUG, f"Removing current position{curr_pos} from list of probable crew cells{self.crew_cells}")

    def remove_success_cell_probs(self, curr_pos):
        ## DO SOMETHING!!
        return

    def init_crew_calcs(self, ship, curr_pos):
        len_crew_cells = len(self.crew_cells)
        print(self.crew_cells)
        for i, key in enumerate(self.crew_cells):
            if i == len_crew_cells - 1:
                break

            self.crew_cells_pair[key] = list()
            cells_pair_list = self.crew_cells_pair[key]
            print(key, "::", end = " ")
            for j in range(i + 1, len_crew_cells):
                print(self.crew_cells[j], end=" ")
                cell_pair = Cell_Pair(key, self.crew_cells[j], ship)
                cell_pair.crew_probs.crew_prob = 1/self.crew_cells_length
                self.update_cell_pair_vals(cell_pair, curr_pos)
                cells_pair_list.append(cell_pair)
            print()

class Alien_Probs:
    def __init__(self):
        self.alien_prob = 0
        self.alien_given_beep_obs = 0
        self.alien_and_beep = 0


""" Core Ship Layout (same as last project) """

class Ship:
    def __init__(self, size, log_level = LOG_INFO):
        self.size = size
        self.grid = [[Cell(i, j, CLOSED_CELL) for j in range(size)] for i in range(size)] # grid is a list of list with each cell as a class
        self.open_cells = []
        self.logger = Logger(log_level)
        self.isBeep = 0
        self.bot = (0, 0)
        self.alien = (0, 0)
        self.crew_1 = (0, 0)
        self.crew_2 = (0, 0)

        self.generate_grid()

    def get_cell(self, cord):
        return self.grid[cord[0]][cord[1]]

    def generate_grid(self):
        self.assign_start_cell()
        self.unblock_closed_cells()
        self.unblock_dead_ends()

    def assign_start_cell(self):
        random_row = randint(0, self.size - 1)
        random_col = randint(0, self.size - 1)
        self.grid[random_row][random_col].cell_type = OPEN_CELL
        self.open_cells.append((random_row, random_col))

    def unblock_closed_cells(self):
        available_cells = self.cells_with_one_open_neighbor(CLOSED_CELL)
        while len(available_cells):
            closed_cell = choice(available_cells)
            self.get_cell(closed_cell).cell_type = OPEN_CELL
            self.open_cells.append(closed_cell)
            available_cells = self.cells_with_one_open_neighbor(CLOSED_CELL)

    def unblock_dead_ends(self):
        dead_end_cells = self.cells_with_one_open_neighbor(OPEN_CELL)
        half_len = len(dead_end_cells)/2

        while half_len > 0:
            dead_end_cells = self.cells_with_one_open_neighbor(OPEN_CELL)
            half_len -= 1
            if len(dead_end_cells):
                continue
            dead_end_cell = choice(dead_end_cells)
            closed_neighbors = get_neighbors(
                self.size, dead_end_cell, self.grid, CLOSED_CELL
            )
            random_cell = choice(closed_neighbors)
            self.get_cell(random_cell).cell_type = OPEN_CELL
            self.open_cells.append(random_cell)

    def cells_with_one_open_neighbor(self, cell_type):
        results = []
        for row in range(self.size):
            for col in range(self.size):
                if ((self.grid[row][col].cell_type & cell_type) and
                    len(get_neighbors(
                        self.size, (row, col), self.grid, OPEN_CELL
                    )) == 1):
                    results.append((row, col))
        return results

    def set_player_cell_type(self):
        self.get_cell(self.bot).cell_type = BOT_CELL
        self.get_cell(self.crew_1).cell_type = CREW_CELL
        self.get_cell(self.crew_2).cell_type = CREW_CELL
        if self.get_cell(self.alien).cell_type & CREW_CELL:
            self.get_cell(self.alien).cell_type |= ALIEN_CELL
        else:
            self.get_cell(self.alien).cell_type = ALIEN_CELL

    def place_crews(self):
        self.bot = choice(self.open_cells)
        self.open_cells.remove(self.bot)
        self.crew_1 = choice(self.open_cells)
        while (True):
            self.crew_2 = choice(self.open_cells)
            if self.crew_2 != self.crew_1:
                break

    def place_players(self):
        self.place_crews()
        self.place_aliens()
        self.open_cells.remove(self.crew_1)
        self.open_cells.remove(self.crew_2)
        for cell_cord in self.open_cells:
            self.init_cell_details(cell_cord)

        for cell in (self.crew_1, self.crew_2, self.bot):
            self.init_cell_details(cell)

        self.set_player_cell_type()

    def init_cell_details(self, cell_cord):
        cell = self.get_cell(cell_cord)
        cell.listen_beep.crew_1_dist = get_manhattan_distance(cell_cord, self.crew_1)
        cell.listen_beep.crew_2_dist = get_manhattan_distance(cell_cord, self.crew_2)
        cell.listen_beep.c1_beep_prob = LOOKUP_E[cell.listen_beep.crew_1_dist]
        cell.listen_beep.c2_beep_prob = LOOKUP_E[cell.listen_beep.crew_2_dist]
        cell.cord = cell_cord

    def place_aliens(self):
        cells_within_zone = self.get_detection_zone(self.bot)
        self.initial_alien_cells = [cell_cord for cell_cord in self.open_cells if cell_cord not in cells_within_zone]
        self.alien = choice(self.initial_alien_cells)

    def get_detection_zone(self, cell):
        k = ALIEN_ZONE_SIZE
        cells_within_zone = []
        min_row = max(0, cell[0] - k)
        max_row = min(self.size - 1, cell[0] + k)
        min_col = max(0, cell[1] - k)
        max_col = min(self.size - 1, cell[1] + k)
        for row in range(min_row, max_row + 1):
            for col in range(min_col, max_col + 1):
                cell = self.grid[row][col]
                cell.within_detection_zone = True
                cells_within_zone.append((row, col))

        return cells_within_zone

    def reset_detection_zone(self, curr_cell):
        cells_within_zone = self.get_detection_zone(curr_cell)

        # Reset cells outside detection zone to false
        for i, cells in enumerate(self.grid):
            for j, cell in enumerate(cells):
                if (i, j) not in cells_within_zone: cell.within_detection_zone = False

        return cells_within_zone

    def get_beep(self, cell, type):
        self.isBeep = uniform(0, 1)
        if (type == 1):
            return True if self.isBeep <= self.get_cell(cell).listen_beep.c1_beep_prob else False
        else:
            return True if self.isBeep <= self.get_cell(cell).listen_beep.c2_beep_prob else False

    def crew_beep(self, cell, crew_count, pending_crew):
        if crew_count == 2:
            if not pending_crew:
                c1_beep = self.get_beep(cell, 1)
                c2_beep = self.get_beep(cell, 2)
                return c1_beep or c2_beep
            else:
                return self.get_beep(cell, pending_crew)
        return self.get_beep(cell, 1)

    def reset_grid(self):
        self.set_player_cell_type()
        for cell in self.open_cells:
            self.get_cell(cell).cell_type = OPEN_CELL


""" Basic search algorithm, and the parent class for our bot """

class SearchAlgo:
    def __init__(self, ship, log_level):
        self.ship = ship
        self.curr_pos = ship.bot
        self.alien_pos = ship.alien
        self.last_pos = ()
        self.logger = Logger(log_level)
        # Working on few issues, will fix it ASAP
        self.alien_calculation_disabled = True

    def search_path(self, dest_cell):
        bfs_queue = []
        visited_cells = set()
        bfs_queue.append((self.curr_pos, [self.curr_pos]))

        while bfs_queue:
            current_cell, path_traversed = bfs_queue.pop(0)
            if current_cell == dest_cell:
                return path_traversed
            elif (current_cell in visited_cells):
                continue

            visited_cells.add(current_cell)
            neighbors = get_neighbors(self.ship.size, current_cell, self.ship.grid, BOT_MOVEMENT_CELLS)
            for neighbor in neighbors:
                if (neighbor not in visited_cells):
                    bfs_queue.append((neighbor, path_traversed + [neighbor]))

        return [] #God forbid, this should never happen


""" Main parent class for all our bots, contain most of the common bot logic """

class ParentBot(SearchAlgo):
    def __init__(self, ship, log_level):
        super(ParentBot, self).__init__(ship, log_level)
        self.alien_evasion_data = Alien_Evasion_Data(ship)
        self.crew_search_data = One_Crew_Search_DS(ship)
        self.total_crew_to_save =  self.total_crew_count = 2
        self.traverse_path = []
        self.pred_crew_cells = []
        self.rescued_crew = self.is_recalc_probs = self.is_keep_moving = False
        self.recalc_pred_cells = True
        self.pending_crew = 0
        self.logger.print_grid(self.ship.grid)
        self.path_traversed = list()
        self.path_traversed.append(self.curr_pos)

    def rescue_info(self):
        init_1_distance = self.ship.get_cell(self.curr_pos).listen_beep.crew_1_dist
        self.logger.print(LOG_INFO, f"Bot{self.curr_pos} needs to find the crew{self.ship.crew_1}")
        init_2_distance = self.ship.get_cell(self.curr_pos).listen_beep.crew_2_dist
        self.logger.print(LOG_INFO, f"Bot{self.curr_pos} needs to find the crew{self.ship.crew_2}")
        return init_1_distance + self.ship.get_cell(self.ship.crew_1).listen_beep.crew_2_dist

    def handle_crew_beep(self):
        self.crew_search_data.is_beep_recv = self.ship.crew_beep(self.curr_pos, self.total_crew_to_save, self.pending_crew)
        track_beep = self.ship.get_cell(self.curr_pos).crew_probs.track_beep
        track_beep[0] += 1
        if self.crew_search_data.is_beep_recv:
            track_beep[1] += 1

    def handle_resuce_opr(self, crew, crew_no, total_iter, idle_steps):
        distance_1 = get_manhattan_distance(crew, self.ship.bot)
        self.logger.print(LOG_INFO, f"Congrats, you found crew member {crew_no} who was initially {distance_1} steps away from you after {total_iter} steps. You moved {total_iter - idle_steps} steps, and waited for {idle_steps} steps")
        self.pending_crew = 2 if (crew_no % 2) else 1
        self.total_crew_count -= 1
        self.rescued_crew = True

    def init_alien_calcs(self):
        return

    def calc_initial_search_data(self):
        self.crew_search_data.init_crew_calcs(self.ship, self.curr_pos)
        self.init_alien_calcs()

    def is_rescued(self, total_iter, idle_steps):
        if (self.curr_pos == self.ship.crew_1) and self.pending_crew != 2:
            self.handle_resuce_opr(self.ship.crew_1, 1, total_iter, idle_steps)
        elif (self.curr_pos == self.ship.crew_2) and self.pending_crew != 1:
            self.handle_resuce_opr(self.ship.crew_2, 2, total_iter, idle_steps)

        return not self.total_crew_count

    def find_traverse_path(self):
        prob_crew_cell = ()
        if len(self.traverse_path) == 0 and len(self.pred_crew_cells) != 0:
            prob_crew_cell = self.pred_crew_cells.pop(0)
            self.traverse_path = self.search_path(prob_crew_cell)
            self.logger.print(LOG_DEBUG, f"New path found, {self.traverse_path}. Pending cells to explore, {self.pred_crew_cells}")
            self.traverse_path.pop(0)

        if len(self.traverse_path) == 0: # some edge case handling
            self.logger.print(LOG_DEBUG, f"Bot in {self.curr_pos} with crew cells {self.crew_search_data.crew_cells} and last prob_crew_cell was {prob_crew_cell}")
            self.logger.print(LOG_NONE, f"Bot in {self.curr_pos} has to find crew({self.total_crew_to_save}) {self.ship.crew_1, self.ship.crew_2} with pending crew {self.pending_crew}")
            self.logger.print(LOG_DEBUG, f"pred_crew_cells::{self.pred_crew_cells}")
            self.logger.print(LOG_NONE, f"path_traversed {self.path_traversed}")
            return False

        return True

    def check_nearby_crew(self):
        return False

    def update_crew_probs_on_movement(self):
        return

    def start_crew_search_data(self):
        check_for_failure(self, 1)
        if self.check_nearby_crew() or self.is_recalc_probs:
            self.update_crew_probs_on_movement()

        # self.logger.print(LOG_DEBUG, f"is_beep_recv::{self.crew_search_data.is_beep_recv}")
        # self.logger.print(LOG_DEBUG, f"beep_prob::{self.crew_search_data.beep_prob}, no_beep_prob::{self.crew_search_data.no_beep_prob}")

    def handle_crew_search_data(self, max_prob, crew_probs, crews_pos_data, pred_crew_cells):
        crew_probs.update_crew_probs(self.crew_search_data)
        if crew_probs.crew_prob not in pred_crew_cells:
            pred_crew_cells[crew_probs.crew_prob] = list()

        pred_crew_cells[crew_probs.crew_prob].append((crews_pos_data, crew_probs.bot_distance))
        if crew_probs.crew_prob > max_prob:
            max_prob = crew_probs.crew_prob

        return max_prob

    def end_crew_search_data(self, max_prob, pred_crew_cells):
        # self.logger.print(LOG_DEBUG, f"beep_prob::{self.crew_search_data.beep_prob}, no_beep_prob::{self.crew_search_data.no_beep_prob}")
        self.logger.print(LOG_DEBUG, f"Bot in {self.curr_pos} has updated crew cells to be, {self.crew_search_data.crew_cells}.")
        self.logger.print_crew_probs(self.ship.grid, self.crew_search_data.is_beep_recv, self.curr_pos)
        return max_prob, pred_crew_cells

    def update_move_vals(self):
        self.is_keep_moving = True if len(self.traverse_path) or len(self.pred_crew_cells) else False
        self.recalc_pred_cells = not self.is_keep_moving

    def update_crew_cells(self):
        self.crew_search_data.remove_cell_probs(self.curr_pos, self.logger, self.curr_pos)
        self.is_recalc_probs = True

    """
        Ideally it is better to move the bot in the direction of the highest prob
        To do this, pred_crew_cells should be sorted based on probabilty
        Remember, we are not taking into account where the alien will be here!!
    """
    def move_bot(self):
        if not self.find_traverse_path():
            return False

        self.ship.get_cell(self.curr_pos).cell_type = OPEN_CELL
        self.last_pos = self.curr_pos
        self.curr_pos = self.traverse_path.pop(0)
        curr_cell = self.ship.get_cell(self.curr_pos)
        self.path_traversed.append(self.curr_pos)
        if (curr_cell.cell_type & CREW_CELL):
            curr_cell.cell_type |= BOT_CELL
            curr_cell.crew_probs.crew_prob = 1
        # elif (curr_cell.cell_type & ALIEN_CELL):
        #     curr_cell.cell_type |= ALIEN_CELL         #  OOPS BYE BYE
        else:
            curr_cell.cell_type = BOT_CELL

        self.update_move_vals()
        self.logger.print(LOG_DEBUG, f"Bot {self.last_pos} has moved to {self.curr_pos} with {self.total_crew_count} crew pending")
        return True

    def move_aliens(self):
        if self.alien_calculation_disabled: return
        alien_moves_possible = get_neighbors(
                self.ship.size,
                self.alien_pos,
                self.ship.grid,
                ALIEN_MOVEMENT_CELLS
            )

        if len(alien_moves_possible) == 0:
            return

        self.logger.print(
            LOG_DEBUG,
            f"Alien has moves {alien_moves_possible}"
        )

        alien_new_pos = choice(alien_moves_possible)

        old_alien_pos = self.alien_pos
        self.alien_pos = alien_new_pos

        if self.ship.grid[alien_new_pos] & BOT_CELL:
            self.logger.print(
                LOG_DEBUG,
                f"Alien moves from current cell {old_alien_pos} to bot cell {alien_new_pos}",
            )
            self.bot_caught_cell = alien_new_pos
            self.ship.grid[alien_new_pos[0]][alien_new_pos[1]].cell_type = BOT_CAUGHT_CELL
            return True

        else:
            self.logger.print(
                LOG_DEBUG,
                f"Alien moves from current cell {self.ship.grid[old_alien_pos]} to open cell {alien_new_pos}",
            )
            self.ship.grid[alien_new_pos[0]][alien_new_pos[1]].cell_type = ALIEN_CELL

        self.ship.grid[old_alien_pos[0]][old_alien_pos[1]].cell_type = OPEN_CELL

        return False


    def start_rescue(self):
        self.logger.print(LOG_NONE, "I am not nice")
        exit()

""" Bot 1 as per given specification """

class Bot_1(ParentBot):
    def __init__(self, ship, log_level = LOG_NONE):
        super(Bot_1, self).__init__(ship, log_level)
        self.override_ship_details()

    def override_ship_details(self):
        self.total_crew_to_save = self.total_crew_count = self.pending_crew = 1
        cell = self.ship.get_cell(self.ship.crew_2)
        if cell.cell_type & ALIEN_CELL:
            self.ship.get_cell(self.ship.crew_2).cell_type = ALIEN_CELL
        else:
            self.ship.get_cell(self.ship.crew_2).cell_type = OPEN_CELL

    def init_alien_calcs(self):
        alien_cell_size = len(self.alien_evasion_data.present_alien_cells)
        for cell_cord in self.alien_evasion_data.present_alien_cells:
            cell = self.ship.grid[cell_cord[0]][cell_cord[1]]
            cell.alien_probs.alien_prob = 1/alien_cell_size

    def update_pred_crew_cells(self, max_prob, pred_crew_cells):
        self.pred_crew_cells = list()
        max_prob_cells = pred_crew_cells[max_prob]
        curr_pos_beeps = self.ship.get_cell(self.curr_pos).crew_probs.track_beep
        curr_pos_fq = curr_pos_beeps[0]/curr_pos_beeps[1] if curr_pos_beeps[1] else 0
        if len(self.last_pos) and curr_pos_fq:
            last_pos_beeps = self.ship.get_cell(self.last_pos).crew_probs.track_beep
            last_pos_fq = last_pos_beeps[0]/last_pos_beeps[1] if last_pos_beeps[1] else 0
            max_prob_cells = sorted(max_prob_cells, key=lambda cell_pair: cell_pair[1], reverse=True)
            if curr_pos_fq > last_pos_fq:
                self.pred_crew_cells.append(max_prob_cells[-1][0])
            elif last_pos_fq > curr_pos_fq:
                self.pred_crew_cells.append(max_prob_cells[0][0])
            elif curr_pos_fq and last_pos_fq == curr_pos_fq:
                pos = round(len(max_prob_cells)/2)
                self.pred_crew_cells.append(max_prob_cells[pos][0])
        else: # can be randomized now...
            self.pred_crew_cells.append(choice(max_prob_cells)[0])
        self.logger.print(LOG_DEBUG, f"The new pred crew cells are {self.pred_crew_cells}")
        return

    def update_crew_probs_on_movement(self):
        self.crew_search_data.set_beeps_prob()
        for cell_cord in self.crew_search_data.crew_cells:
            cell = self.ship.get_cell(cell_cord)
            self.crew_search_data.update_cell_mov_vals(cell.crew_probs, self.curr_pos, cell_cord)

    def check_nearby_crew(self):
        if self.crew_search_data.is_beep_recv:
            return False # no need to check nearby cells when we get a beep

        neighbors = get_neighbors(self.ship.size, self.curr_pos, self.ship.grid, BOT_MOVEMENT_CELLS)
        neighbors_in_crew = [neighbor for neighbor in neighbors if neighbor in self.crew_search_data.crew_cells]
        if (len(neighbors_in_crew)):
            for neighbor in neighbors_in_crew:
                self.crew_search_data.remove_cell_probs(neighbor, self.logger, self.curr_pos)
                if neighbor in self.pred_crew_cells:
                    self.pred_crew_cells.remove(neighbor)

                if self.is_keep_moving:
                    self.update_move_vals()

            # removing cells from total probs, normalizing our values is the same as, prob(a|¬b,¬c,¬d)=prob(a)/(1-p(¬b)-p(¬c)-p(¬d)))
            self.logger.print(LOG_DEBUG, f"Following cells {neighbors_in_crew}, were removed from crew cells {self.crew_search_data.crew_cells} and pred cells {self.pred_crew_cells}")
            return True
        return False

    def update_crew_search_data(self):
        beep_prob = no_beep_prob = 0.0
        pred_crew_cells = dict()
        max_prob = 0
        self.start_crew_search_data()
        for cell_cord in self.crew_search_data.crew_cells:
            cell = self.ship.get_cell(cell_cord)
            crew_probs = cell.crew_probs
            self.logger.print_cell_data(LOG_DEBUG, crew_probs, cell.cord, self.curr_pos)
            check_for_failure(self, 2)
            max_prob = self.handle_crew_search_data(max_prob, crew_probs, cell_cord, pred_crew_cells)
            beep_prob += crew_probs.crew_and_beep
            no_beep_prob += crew_probs.crew_and_no_beep

        self.crew_search_data.set_beeps_prob(beep_prob, no_beep_prob)
        return self.end_crew_search_data(max_prob, pred_crew_cells)

    def compute_likely_alien_movements(self):
        if self.alien_calculation_disabled: return
        alien_cells = self.alien_evasion_data.present_alien_cells # N at any point t
        prob_cell_mapping = dict()

        for cell_cord in alien_cells:
            cell = self.ship.grid[cell_cord[0]][cell_cord[1]]
            prob_cell_mapping[cell_cord] = cell.alien_probs.alien_prob
            cell.alien_probs.alien_prob = 0

        self.logger.print(
            LOG_DEBUG, f"alien_cells::{alien_cells}, prob_cell_mapping::{prob_cell_mapping}"
        )

        for cell_cord in alien_cells:
            cell = self.ship.grid[cell_cord[0]][cell_cord[1]]
            cell_prob = prob_cell_mapping[cell_cord]
            possible_alien_moves = get_neighbors(
                self.ship.size,
                cell_cord,
                self.ship.grid,
                ALIEN_MOVEMENT_CELLS
            )

            total_moves = len(possible_alien_moves)

            if(total_moves == 0):
                cell.alien_probs.alien_prob = cell_prob
                continue

            for alien_move in possible_alien_moves:
                new_cell = self.ship.grid[alien_move[0]][alien_move[1]]
                new_cell.alien_probs.alien_prob += cell_prob/total_moves
                self.logger.print(
                    LOG_DEBUG, f"alien_cells::{alien_cells}, prob_cell_mapping::{prob_cell_mapping}"
                )

        prob_cell_mapping.clear()

        if self.logger.log_level == LOG_DEBUG:
            for cell_cord in alien_cells:
                cell = self.ship.grid[cell_cord[0]][cell_cord[1]]
                self.logger.print(LOG_DEBUG, f"Now the cell.alien_prob for cell_cord::{cell_cord} is {cell.alien_probs.alien_prob}")

    '''
        If beep heard, cells within detection zone: P(B obs /A) = 1
        cells outside P(B obs /A) = 0
        If beep not heard, cells within detection zone: P(B obs /A) = 0
        cells outside P(B obs /A) = 1
        P(A/B obs) = P(B obs/ A) P(A) / P(B obs)
    '''
    def calc_alien_probs(self):
        if self.alien_calculation_disabled: return
        alien_cells = self.alien_evasion_data.all_alien_cells
        beep_recv = self.alien_evasion_data.is_beep_recv

        prob_alien_in_inner_cells = ALIEN_PRESENT if beep_recv else ALIEN_NOT_PRESENT
        prob_alien_in_outer_cells = ALIEN_PRESENT if (not beep_recv) else ALIEN_NOT_PRESENT

        for cell_cord in alien_cells:
            cell = self.ship.grid[cell_cord[0]][cell_cord[1]]

            prob_beep_gv_alien = prob_alien_in_inner_cells if cell.within_detection_zone else prob_alien_in_outer_cells
            cell.alien_probs.alien_and_beep = prob_beep_gv_alien * cell.probs.alien_prob

            # cell.probs.alien_given_beep_obs =
            continue
        pass

    def rescue_info(self):
        if self.total_crew_to_save == 1:
            init_1_distance = self.ship.get_cell(self.curr_pos).listen_beep.crew_1_dist
            self.logger.print(LOG_INFO, f"Bot{self.curr_pos} needs to find the crew{self.ship.crew_1}")
            return init_1_distance
        else:
            return super(Bot_1, self).rescue_info()

    # repeat, to be shifted to a common class!!
    def start_rescue(self):
        is_move_bot = False
        beep_counter = idle_steps = total_iter = 0
        init_distance = self.rescue_info()

        self.calc_initial_search_data()
        while (True): # Keep trying till you find the crew
            total_iter += 1

            # Alien beep logic
            alien_cell = self.ship.grid[self.alien_pos[0]][self.alien_pos[1]]
            self.alien_evasion_data.is_beep_recv = alien_cell.within_detection_zone
            self.logger.print(
                LOG_DEBUG,
                f"alien_pos:{self.alien_pos}, within_detection_zone::{alien_cell.within_detection_zone}"
            )

            self.handle_crew_beep()
            max_prob, pred_crew_cells = self.update_crew_search_data()
            self.calc_alien_probs()
            if self.recalc_pred_cells:
                self.update_pred_crew_cells(max_prob, pred_crew_cells)

            if (self.is_keep_moving or is_move_bot) and self.move_bot():
                if self.is_rescued(total_iter, idle_steps):
                    return (init_distance, total_iter, idle_steps)

                self.update_crew_cells()
                beep_counter = 0
                is_move_bot = False
                self.ship.reset_detection_zone(self.curr_pos)
            else:
                is_move_bot = False
                idle_steps += 1

            if self.move_aliens():
                return

            # update probability of alien movement based on current P(A), cell.alien_prob
            self.compute_likely_alien_movements()

            beep_counter += 1
            if beep_counter >= (IDLE_BEEP_COUNT - 1):
                is_move_bot = True
                self.update_move_vals()

class Bot_3(Bot_1):
    def __init__(self, ship, log_level = LOG_NONE):
        super(Bot_3, self).__init__(ship, log_level)
        self.override_ship_details()

    def handle_resuce_opr(self, crew, crew_no, total_iter, idle_steps):
        super(Bot_3, self).handle_resuce_opr(crew, crew_no, total_iter, idle_steps)
        self.crew_search_data.init_crew_calcs(self.ship, self.curr_pos)

    def override_ship_details(self):
        self.total_crew_to_save = self.total_crew_count = 2
        self.pending_crew = 0
        cell = self.ship.get_cell(self.ship.crew_2)
        if cell.cell_type & ALIEN_CELL:
            self.ship.get_cell(self.ship.crew_2).cell_type |= CREW_CELL
        else:
            self.ship.get_cell(self.ship.crew_2).cell_type = CREW_CELL

class Bot_4(ParentBot):
    def __init__(self, ship, log_level = LOG_NONE):
        super(Bot_4, self).__init__(ship, log_level)
        self.crew_search_data = Two_Crew_Search_DS(ship)

    def update_pred_crew_cells(self, max_prob, pred_crew_cells):
        self.pred_crew_cells = list()
        cell_pair = None
        max_prob_cells = pred_crew_cells[max_prob]
        curr_pos_beeps = self.ship.get_cell(self.curr_pos).crew_probs.track_beep
        curr_pos_fq = curr_pos_beeps[0]/curr_pos_beeps[1] if curr_pos_beeps[1] else 0
        if len(self.last_pos) and curr_pos_fq:
            last_pos_beeps = self.ship.get_cell(self.last_pos).crew_probs.track_beep
            last_pos_fq = last_pos_beeps[0]/last_pos_beeps[1] if last_pos_beeps[1] else 0
            max_prob_cells = sorted(max_prob_cells, key=lambda cell_pair: cell_pair[1], reverse=True)
            if curr_pos_fq > last_pos_fq:
                cell_pair = max_prob_cells[-1][0]
            elif last_pos_fq > curr_pos_fq:
                cell_pair = max_prob_cells[0][0]
            else:
                pos = round(len(max_prob_cells)/2)
                cell_pair = max_prob_cells[pos][0]
        else: # can be randomized now...
            cell_pair = choice(max_prob_cells)[0]

        distance_0 = get_manhattan_distance(cell_pair.cell_1.cord, cell_pair.cell_2.cord)
        distance_1 = get_manhattan_distance(self.curr_pos, cell_pair.cell_1.cord) + distance_0
        distance_2 = get_manhattan_distance(self.curr_pos, cell_pair.cell_2.cord) + distance_0
        if distance_1 > distance_2:
            self.pred_crew_cells.append(cell_pair.cell_2.cord)
            self.pred_crew_cells.append(cell_pair.cell_1.cord)
        else:
            self.pred_crew_cells.append(cell_pair.cell_1.cord)
            self.pred_crew_cells.append(cell_pair.cell_2.cord)

        self.logger.print(LOG_DEBUG, f"The new pred crew cells are {self.pred_crew_cells}")
        return

    def update_crew_probs_on_movement(self):
        self.crew_search_data.set_beeps_prob()
        for key in self.crew_search_data.crew_cells_pair:
            cell_pair_list = self.crew_search_data.crew_cells_pair[key]
            for cell_pair in cell_pair_list:
                self.crew_search_data.update_cell_pair_vals(cell_pair, self.curr_pos, self.pending_crew)

    def check_nearby_crew(self):
        if self.crew_search_data.is_beep_recv:
            return False # no need to check nearby cells when we get a beep

        neighbors = get_neighbors(self.ship.size, self.curr_pos, self.ship.grid, BOT_MOVEMENT_CELLS)
        neighbors_in_crew = [neighbor for neighbor in neighbors if neighbor in self.crew_search_data.crew_cells]
        if (len(neighbors_in_crew)):
            for neighbor in neighbors_in_crew:
                if self.total_crew_count == 1:
                    self.crew_search_data.remove_success_cell_probs(self.curr_pos)
                else:
                    self.crew_search_data.remove_cell_probs(neighbor, self.logger, self.curr_pos)
                if neighbor in self.pred_crew_cells:
                    self.pred_crew_cells.remove(neighbor)

                if self.is_keep_moving:
                    self.update_move_vals()

            # removing cells from total probs, normalizing our values is the same as, prob(a|¬b,¬c,¬d)=prob(a)/(1-p(¬b)-p(¬c)-p(¬d)))
            self.logger.print(LOG_DEBUG, f"Following cells {neighbors_in_crew}, were removed from crew cells {self.crew_search_data.crew_cells} and pred cells {self.pred_crew_cells}")
            return True
        return False

    def update_crew_search_data(self):
        beep_prob = no_beep_prob = 0.0
        pred_crew_cells = dict()
        max_prob = 0
        self.start_crew_search_data()
        for key in self.crew_search_data.crew_cells_pair:
            cell_pair_list = self.crew_search_data.crew_cells_pair[key]
            for cell_pair in cell_pair_list:
                crew_probs = cell_pair.crew_probs
                crew_probs.update_crew_probs(self.crew_search_data)
                if self.recalc_pred_cells:
                    distance_0 = get_manhattan_distance(cell_pair.cell_1.cord, cell_pair.cell_2.cord)
                    distance_1 = get_manhattan_distance(self.curr_pos, cell_pair.cell_1.cord) + distance_0
                    distance_2 = get_manhattan_distance(self.curr_pos, cell_pair.cell_2.cord) + distance_0
                    crew_probs.bot_distance = distance_1 if distance_1 < distance_2 else distance_2
                max_prob = self.handle_crew_search_data(max_prob, crew_probs, cell_pair, pred_crew_cells)
                beep_prob += crew_probs.crew_and_beep
                no_beep_prob += crew_probs.crew_and_no_beep

        self.crew_search_data.set_beeps_prob(beep_prob, no_beep_prob)
        return self.end_crew_search_data(max_prob, pred_crew_cells)

    def update_success_cells(self):
        self.crew_search_data.remove_success_cell_probs(self.curr_pos)

    def update_crew_cells(self):
        if self.total_crew_count == 1:
            self.crew_search_data.remove_success_cell_probs(self.curr_pos)
        else:
            super(Bot_4, self).update_crew_cells()


    # repeat, to be shifted to a common class!!
    def start_rescue(self):
        is_move_bot = False
        beep_counter = idle_steps = total_iter = 0
        init_distance = self.rescue_info()

        self.calc_initial_search_data()
        while(True):
            self.ship.logger.print_grid(self.ship.grid)
            total_iter += 1

            self.handle_crew_beep()
            # self.calc_alien_probs()
            max_prob, pred_crew_cells = self.update_crew_search_data()
            if self.recalc_pred_cells:
                self.update_pred_crew_cells(max_prob, pred_crew_cells)

            if (self.is_keep_moving or is_move_bot) and self.move_bot():
                if self.is_rescued(total_iter, idle_steps):
                    return (init_distance, total_iter, idle_steps)

                if self.rescued_crew:
                    self.update_success_cells()
                else:
                    self.update_crew_cells()
                beep_counter = 0
                is_move_bot = False
                self.ship.reset_detection_zone(self.curr_pos)
            else:
                is_move_bot = False
                idle_steps += 1

            if self.move_aliens():
                return

            # update probability of alien movement based on current P(A), cell.alien_prob
            # self.compute_likely_alien_movements()

            beep_counter += 1
            if beep_counter >= (IDLE_BEEP_COUNT - 1):
                is_move_bot = True


"""Simulation & Testing logic begins"""

BOT_NAMES = {
    0 : "bot_1",
    1 : "bot_3",
    2 : "bot_4"
}

# Responsible for updating the alpha for each worker pool
def update_lookup(alpha):
    global LOOKUP_E, LOOKUP_NOT_E, ALPHA
    ALPHA = alpha
    LOOKUP_E = [pow(exp, (-1*ALPHA*(i - 1))) for i in range(GRID_SIZE*2 + 1)]
    LOOKUP_NOT_E = [(1-LOOKUP_E[i]) for i in range(GRID_SIZE*2 + 1)]

def bot_factory(itr, ship, log_level = LOG_NONE):
    if (itr == 0):
        return Bot_1(ship, log_level)
    if (itr == 1):
        return Bot_3(ship, log_level)
    elif (itr == 2):
        return Bot_4(ship, log_level)
    return ParentBot(ship, log_level)

# Test function
def run_test(log_level = LOG_INFO):
    update_lookup(ALPHA)
    ship = Ship(GRID_SIZE)
    ship.place_players()
    for i in range(TOTAL_BOTS):
        print(BOT_NAMES[i])
        begin = time()
        bot = bot_factory(i, ship, log_level)
        bot.start_rescue()
        end = time()
        print(end - begin)
        del bot
        ship.reset_grid()
    del ship

# Runs n number of iteration for each bot for given alpha value
def run_sim(iterations_range, queue, alpha_range):
    alpha_dict = dict()
    for alpha in alpha_range:
        update_lookup(alpha)
        temp_data_set = [[0.0 for i in range(4)] for j in range(TOTAL_BOTS)]
        for itr in iterations_range:
            print(itr+1, end = '\r')
            ship = Ship(GRID_SIZE, LOG_DEBUG_GRID)
            # CREW LIST
            ship.place_players()
            # ship.logger.print_grid(ship.grid)
            for bot_no in range(TOTAL_BOTS):
                # bot = Bot_1(ship)
                bot = bot_factory(bot_no, ship)
                begin = time()
                ret_vals = bot.start_rescue()
                end = time()
                for resc_val in range(3):
                    temp_data_set[bot_no][resc_val] += ret_vals[resc_val]
                temp_data_set[bot_no][3] += (end-begin)
                ship.reset_grid()
                del bot
            del ship
        alpha_dict[alpha] = temp_data_set
    queue.put(alpha_dict)

# Creates "n" process, and runs multiple simulation for same value of alpha simulataenously
def run_multi_sim(alpha_range, is_print = False):
    begin = time()
    alpha_dict = dict()
    data_set = [[0.0 for i in range(4)] for j in range(TOTAL_BOTS)]
    processes = []
    queue = Queue()
    if (is_print):
        print(f"Iterations begin...")
    core_count = cpu_count()
    total_iters = round(TOTAL_ITERATIONS/core_count)
    actual_iters = total_iters * core_count
    for itr in range(core_count):
        p = Process(target=run_sim, args=(range(itr*total_iters, (itr+1)*total_iters), queue, alpha_range))
        processes.append(p)
        p.start()

    for proc in processes:
        proc.join()
        temp_alpha_dict = queue.get()
        for alpha, value in temp_alpha_dict.items():
            if alpha not in alpha_dict:
                alpha_dict[alpha] = value
            else:
                for i, val_range in enumerate(value):
                    for j, resc_vals in enumerate(val_range):
                        alpha_dict[alpha][i][j] += resc_vals

    for alpha, value in alpha_dict.items():
        for bot_no in range(TOTAL_BOTS):
            for resc_val in range(4):
                value[bot_no][resc_val] = value[bot_no][resc_val]/actual_iters
    end = time()

    if (is_print):
        for alpha, resc_val in alpha_dict.items():
            print()
            print(f"Grid Size:{GRID_SIZE} for {actual_iters} iterations took time {end-begin} for alpha {alpha}")
            print ("%20s %20s %20s %20s %20s %20s" % ("Bot", "Distance", "Total Iterations", "Idle steps", "Steps moved", "Time taken"))
            for itr, value in enumerate(resc_val):
                print("%20s %20s %20s %20s %20s %20s" % (BOT_NAMES[itr], value[0], value[1], value[2], value[1]-value[2], value[3]))
    else:
        print(f"Grid Size:{GRID_SIZE} for {actual_iters} iterations took total time {end-begin} for alpha range {alpha_dict.keys()}")

    del queue
    del processes
    return alpha_dict

# Runs multiple simulations for multiple values of alpha concurrently
def compare_multiple_alpha():
    global ALPHA
    alpha_range = [round(ALPHA + (ALPHA_STEP_INCREASE * i), 2) for i in range(MAX_ALPHA_ITERATIONS)]
    alpha_dict = run_multi_sim(alpha_range)
    print ("%20s %20s %20s %20s %20s %20s" % ("Bot", "Distance", "Total Iterations", "Idle steps", "Steps moved", "Time taken"))
    for alpha, resc_val in alpha_dict.items():
        print(f"{'*'*61}{alpha}{'*'*62}")
        for itr, value in enumerate(resc_val):
            print("%20s %20s %20s %20s %20s %20s" % (BOT_NAMES[itr], value[0], value[1], value[2], value[1]-value[2], value[3]))


if __name__ == '__main__':
    run_test()
    # run_multi_sim([ALPHA], True)
    # compare_multiple_alpha()
