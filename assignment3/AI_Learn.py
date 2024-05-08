import AI_Proj3
import run_simulations
from multiprocessing import cpu_count
from run_simulations import DETAILS
from pandas import read_csv
from ast import literal_eval
import torch
from matplotlib import pylab as plt
from sklearn.model_selection import train_test_split
from torch import nn
import torch.nn.functional as F
from time import time
import numpy as np
from os import path
import random
import csv

MAX_TEST = 1000
MAX_TRAIN = 1000
MAX_PROCESS=int(cpu_count()/2)
GENERAL_TRAIN = int(96/MAX_PROCESS)
GENERAL_TEST = int(108/MAX_PROCESS)

AI_Proj3.GRID_SIZE = 7
AI_Proj3.TOTAL_ELEMENTS = 4
AI_Proj3.RAND_CLOSED_CELLS = 10
LEARNING_RATE=1e-2
IS_TEST_SETUP = False
if IS_TEST_SETUP:
    FULL_GRID_STATE = (AI_Proj3.RAND_CLOSED_CELLS + 4 + 2)
else:
    FULL_GRID_STATE = AI_Proj3.TOTAL_ELEMENTS*AI_Proj3.GRID_SIZE**2

H_LAYERS = [int(FULL_GRID_STATE*2.5), int(FULL_GRID_STATE*1.75), int(FULL_GRID_STATE*2.5)]
# H_LAYERS = [FULL_GRID_STATE*2, int(FULL_GRID_STATE*1.5), FULL_GRID_STATE*2]
# H_LAYERS = [FULL_GRID_STATE*2.5, int(FULL_GRID_STATE*1.75), int(FULL_GRID_STATE*1.75), FULL_GRID_STATE*2.5]
BOT_ACTIONS = 9
AI_Proj3.VISUALIZE = False

DEVICE = 'cuda' if torch.cuda.is_available() else 'cpu'
IS_DEBUG = False

ACTIONS_ID = {
"IDLE" : int(0),
"NORTH" : int(1),
"SOUTH" : int(5),
"EAST" : int(3),
"WEST" : int(7),
"NORTH_EAST" : int(2),
"NORTH_WEST" : int(8),
"SOUTH_EAST" : int(4),
"SOUTH_WEST" : int(6)
}

class HIDDEN_UNITS(nn.Module):
    def __init__(self, in_channels, out_channels, activation):
        super(HIDDEN_UNITS, self).__init__()
        self.activation = activation
        self.nn = nn.Linear(in_channels, out_channels, device=DEVICE)

    def forward(self, x):
        out = self.nn(x)
        out = self.activation(out)
        return out

class QModel(nn.Module):
    def __init__(self, in_channels, hidden_layers, out_channels, activation = F.relu):
        super(QModel, self).__init__()
        assert type(hidden_layers) is list
        self.hidden_units = nn.ModuleList()
        self.in_channels = in_channels
        prev_layer = in_channels
        for hidden in hidden_layers:
            self.hidden_units.append(HIDDEN_UNITS(prev_layer, hidden, activation))
            prev_layer = hidden
        self.final_unit = nn.Linear(prev_layer, out_channels)

    def forward(self, x):
        out = x.view(-1,self.in_channels).float()
        for unit in self.hidden_units:
            out = unit(out)
        out = self.final_unit(out)
        return out

class LEARN_CONFIG(AI_Proj3.SHIP):
    def __init__(self, model_data, is_import = False):
        super(LEARN_CONFIG, self).__init__(is_import)
        self.q_model = model_data
        self.optimizer = torch.optim.Adam(self.q_model.parameters(), lr=LEARNING_RATE)
        # self.optimizer = torch.optim.SGD(self.q_model.parameters(), lr=LEARNING_RATE)
        self.loss_fn = torch.nn.CrossEntropyLoss()
        self.loss_fn = self.loss_fn.to(torch.device(DEVICE))
        self.total_failure_moves = self.total_success_moves = 0
        self.losses = []

    def import_ship(self, file_name="layout.csv"):
        with open(file_name, 'r', newline='') as csvfile:
            reader = csv.reader(csvfile)
            for data in reader:
                closed_cells_str = literal_eval(str(data))
                for cell_str in closed_cells_str:
                    cell = literal_eval(cell_str)
                    self.closed_cells.append(cell)
                    self.open_cells.remove(cell)
                    self.set_state(cell, AI_Proj3.CLOSED_CELL)

        self.set_teleport()
        self.place_players()

    def print_losses(self):
        # plt.figure(figsize=(10,7))
        # plt.plot(self.losses)
        # plt.xlabel("Epochs",fontsize=22)
        # plt.ylabel("Loss",fontsize=22)
        # plt.show(block=False)
        # plt.pause(1)
        # plt.close()
        print(self.total_failure_moves, self.total_success_moves, self.total_failure_moves/(self.total_failure_moves+self.total_success_moves), len(self.losses))
        self.total_failure_moves = self.total_success_moves = 0
        self.losses.clear()

    def get_action(self, bot_cell, bot_move):
        val = -1
        if bot_cell and bot_move:
            delta_x = bot_move[0] - bot_cell[0]
            delta_y = bot_move[1] - bot_cell[1]

            if delta_x == 0 and delta_y == 0:
                val = ACTIONS_ID["IDLE"]
            elif delta_x == 0:
                val = ACTIONS_ID["NORTH"] if delta_y > 0 else ACTIONS_ID["SOUTH"]
            elif delta_y == 0:
                val = ACTIONS_ID["EAST"] if delta_x > 0 else ACTIONS_ID["WEST"]
            elif delta_x > 0:
                val = ACTIONS_ID["NORTH_EAST"] if delta_y > 0 else ACTIONS_ID["SOUTH_EAST"]
            else:
                val = ACTIONS_ID["NORTH_WEST"] if delta_y > 0 else ACTIONS_ID["SOUTH_WEST"]
        return val

    def get_ship_layout(self, bot_pos, crew_pos):
        if not IS_TEST_SETUP:
            rows = []
            for i in range(self.size):
                cols = []
                for j in range(self.size):
                    curr_state = self.get_state((i, j))
                    states = []
                    states.append(1 if curr_state == AI_Proj3.CLOSED_CELL else 0)
                    states.append(1 if curr_state == AI_Proj3.TELEPORT_CELL else 0)
                    states.append(1 if (i, j) == bot_pos else 0)
                    states.append(1 if (i, j) == crew_pos else 0)
                    cols.extend(states)

                rows.extend(cols)

        else:
            bot_code = bot_pos[0]*self.size + bot_pos[1]
            crew_code = crew_pos[0]*self.size + crew_pos[1]
            teleport_code = self.teleport_cell[0]*self.size + self.teleport_cell[1]
            rows = [bot_code, crew_code, teleport_code]
            for cell in self.closed_cells:
                closed_code = cell[0]*self.size + cell[1]
                rows.append(closed_code)

        final = (np.asarray(rows, dtype=np.float64))
        return final

    def train_model(self):
        self.dataframe = read_csv("values.csv")
        self.dataframe["Ship_layout"] = self.dataframe.apply(lambda row: self.get_ship_layout(literal_eval(row['Bot_Pos']), literal_eval(row['Crew_Pos'])), axis=1)
        print(self.closed_cells)
        print(self.dataframe)
        input_tensor = torch.from_numpy(np.array([data for data in self.dataframe['Ship_layout']]))
        input_tensor = input_tensor.to(torch.device(DEVICE))
        output_tensor = torch.tensor([data for data in self.dataframe['Action']])
        output_tensor = output_tensor.to(torch.device(DEVICE))
        x_train, x_test, y_train, y_test = train_test_split(input_tensor, output_tensor, shuffle=True)
        for itr in range(1000):
            print(itr, end="\r")
            logits = self.q_model(x_train)
            loss = self.loss_fn(logits, y_train)
            if (itr+1) % 1000 == 0:
                print(x_train, y_train, logits)
            loss.backward()
            self.optimizer.step()

        print()
        pred_logits_test = self.q_model(x_test)
        print("torch_sum", torch.sum( y_test == torch.argmax( pred_logits_test, dim = 1 ) ) / y_test.shape[0])

class Q_BOT(AI_Proj3.BOT_CONFIG):
    def __init__(self, ship, epsilon):
        super(Q_BOT, self).__init__(ship)
        self.old_bot_pos = ()
        self.old_crew_pos = ()
        self.state_1 = self.ship.get_ship_layout(self.local_bot_pos, self.local_crew_pos)
        self.tensor_1 = torch.from_numpy(self.state_1).float()
        self.tensor_1 = self.tensor_1.to(torch.device(DEVICE))
        self.state_2 = np.array([])
        self.is_train = True
        self.local_check = 0
        self.epsilon = epsilon
        self.legal_moves = []

    def make_action(self):
        move = self.local_all_moves[self.action_no]
        next_pos = (self.local_bot_pos[0] + move[0], self.local_bot_pos[1] + move[1])
        self.action_result = AI_Proj3.CLOSED_CELL

        if (self.is_train and 0 < next_pos[0] < self.ship.size and 0 < next_pos[1] < self.ship.size) or (not self.is_train and 0 <= next_pos[0] < self.ship.size and 0 <= next_pos[1] < self.ship.size):
            state = self.ship.get_state(next_pos)
            self.action_result = state
            if state != AI_Proj3.CLOSED_CELL and state != AI_Proj3.CREW_CELL:
                self.make_bot_move(next_pos)
                return


    def calc_loss(self):
        bot_pos = self.local_bot_pos
        crew_pos = self.local_crew_pos
        self.state_2 = self.ship.get_ship_layout(bot_pos, crew_pos)
        self.tensor_2 = torch.from_numpy(self.state_2).float()
        self.tensor_2 = self.tensor_2.to(torch.device(DEVICE))
        # with torch.no_grad():
        #     possibleQs = self.ship.q_model(self.tensor_2)
        # newQ = GAAMA*possibleQs[action_no].item() - reward if self.local_crew_pos != self.ship.teleport_cell else 0
        # self.policy_reward = torch.Tensor([newQ]).detach()
        # self.policy_action = self.q_vals.squeeze()[self.action_no]
        # print(self.policy_action, self.policy_reward)
        # loss = self.ship.loss_fn(self.policy_action, self.policy_reward)

        # action_list = [0.0]*BOT_ACTIONS
        # action_list[self.best_action] = 1.0

        if self.action_no != self.best_action:
            self.ship.total_failure_moves += 1
        else:
            self.ship.total_success_moves += 1

        output = torch.Tensor([self.best_action]).long()
        # loss = self.ship.loss_fn(self.q_vals, torch.Tensor(action_list))
        output = output.to(torch.device(DEVICE))
        loss = self.ship.loss_fn(self.q_vals, output)

        if IS_DEBUG and self.total_moves % 500 == 0 or self.local_check:
            self.ship.print_ship()
            self.local_check += 1
            print(self.best_action, self.local_all_moves[self.best_action], self.action_no, self.local_all_moves[self.action_no], self.best_move)
            print(self.q_vals, output, loss)
            if self.local_check == 3:
                self.local_check = 0

        if (self.is_train):
            self.ship.optimizer.zero_grad()
            loss.backward()
            self.ship.losses.append(loss.item())
            self.ship.optimizer.step()
        else:
            loss.backward()
            self.ship.losses.append(loss.item())

        self.state_1 = self.state_2
        self.tensor_1 = self.tensor_2

    def process_q_learn(self):
        self.q_vals = self.ship.q_model(self.tensor_1)
        self.best_move = self.ship.best_policy_lookup[self.local_bot_pos][self.local_crew_pos][AI_Proj3.BEST_MOVE]
        self.best_action = self.ship.get_action(self.local_bot_pos, self.best_move)
        if random.uniform(0, 1) < self.epsilon:
            self.action_no = np.random.randint(0,9)
        else:
            self.action_no = np.argmax(self.q_vals.data.numpy())

        self.make_action()
        return self.move_crew()

    def move_bot(self):
        if IS_DEBUG and self.total_moves % 500 == 0 or self.local_check:
            self.ship.print_ship()

        self.q_vals = self.ship.q_model(self.tensor_1)
        self.action_no = np.argmax(self.q_vals.data.numpy())
        self.best_move = self.ship.best_policy_lookup[self.local_bot_pos][self.local_crew_pos][AI_Proj3.BEST_MOVE]
        self.best_action = self.ship.get_action(self.local_bot_pos, self.best_move)
        self.make_action()

    def move_crew(self):
        ret_val = super(Q_BOT, self).move_crew()
        self.calc_loss()
        return ret_val

    def train_rescue(self):
        self.is_train = True
        self.total_moves = 0
        if self.ship.get_state(self.local_crew_pos) & AI_Proj3.TELEPORT_CELL:
            return self.total_moves, AI_Proj3.SUCCESS

        while(True):
            self.total_moves += 1
            # self.visualize_grid(False)
            if self.process_q_learn():
                # self.visualize_grid()
                return self.total_moves, AI_Proj3.SUCCESS

            if self.total_moves > 1000:
                # self.visualize_grid()
                return self.total_moves, AI_Proj3.FAILURE

    def test_rescue(self):
        self.is_train = False
        return self.start_rescue()

def t_bot(ship, is_train = True):
    epochs = MAX_TRAIN if is_train else MAX_TEST
    avg_moves = DETAILS()
    epsilon = 1.0
    for iters in range(epochs):
        # print(iters, end='\r')
        q_bot = Q_BOT(ship, epsilon)
        if is_train:
            moves, result = q_bot.train_rescue()
        else:
            moves, result = q_bot.test_rescue()

        if result:
            avg_moves.update_min_max(moves)
            avg_moves.s_moves += moves
            avg_moves.success += 1
        else:
            avg_moves.f_moves += moves
            avg_moves.failure += 1

        avg_moves.distance += AI_Proj3.get_manhattan_distance(ship.bot_pos, ship.crew_pos)
        avg_moves.dest_dist += AI_Proj3.get_manhattan_distance(ship.crew_pos, ship.teleport_cell)
        del q_bot

        if epsilon > 0.1:
            epsilon -= (1/epochs)

        ship.reset_positions()

    # print()
    avg_moves.get_avg(epochs)
    if not is_train:
        print_data(avg_moves)
    return avg_moves

def single_sim(ship):
    final_data = run_simulations.run_sim([range(0, MAX_TEST), ship])

    run_simulations.print_header(MAX_TEST)
    for itr in range(run_simulations.TOTAL_CONFIGS):
        run_simulations.print_data(final_data, itr, MAX_TEST)

def store_ship(ship):
    with open("layout.csv", 'w', newline='') as csvfile:
        layout = csv.writer(csvfile)
        layout.writerow([cell for cell in ship.closed_cells])

    with open("values.csv", 'w', newline='') as csvfile:
        values = csv.writer(csvfile)
        values.writerow(['Bot_Pos', 'Crew_Pos', 'Move', 'Action'])
        for bot_pos in ship.best_policy_lookup:
            for crew_pos in ship.best_policy_lookup[bot_pos]:
                move = ship.best_policy_lookup[bot_pos][crew_pos][AI_Proj3.BEST_MOVE]
                action = ship.get_action(bot_pos, move)
                values.writerow([bot_pos, crew_pos, move, action])

def test_new():
    q_model = QModel(FULL_GRID_STATE, H_LAYERS, BOT_ACTIONS)
    ship = LEARN_CONFIG(q_model)
    ship.perform_initial_calcs()
    store_ship(ship)
    del ship
    ship = LEARN_CONFIG(False, True)
    ship.import_ship()
    ship.train_model()
    ship.perform_initial_calcs()
    t_bot(ship, False)
    ship.print_losses()

def single_run():
    q_model = QModel(FULL_GRID_STATE, H_LAYERS, BOT_ACTIONS)
    ship = LEARN_CONFIG(q_model)
    ship.perform_initial_calcs()
    t_bot(ship)
    ship.print_losses()
    t_bot(ship, False)
    ship.print_losses()
    single_sim(ship)

def train(q_model):
    if DEVICE == "cuda":
        torch.cuda.set_device(torch.device('cuda:0'))

    for i in range(int(GENERAL_TRAIN)):
        ship = LEARN_CONFIG(q_model)
        ship.perform_initial_calcs()
        t_bot(ship)
        ship.print_losses()

def test(q_model):
    if DEVICE == "cuda":
        torch.cuda.set_device(torch.device('cuda:0'))

    for i in range(int(GENERAL_TEST)):
        ship = LEARN_CONFIG(q_model)
        ship.perform_initial_calcs()
        t_bot(ship, False)
        ship.print_losses()

def print_data(detail):
    print("%18s %18s %18s %18s %18s %18s %18s %18s %18s %18s" % ("Avg Suc Moves", "Success Rate", "Min Suc. Moves", "Max Suc. Moves", "Avg Caught Moves", "Caught Rate", "Avg Fail Moves", "Failure Rate", "Avg Bot Crew Dist", "Crew Teleport Dist"))
    print(("%18s %18s %18s %18s %18s %18s %18s %18s %18s %18s" % (detail.s_moves, detail.success, detail.min_success, detail.max_success, detail.c_moves, detail.caught, detail.f_moves, detail.failure, detail.distance, detail.dest_dist)))

def multi_run():
    if DEVICE == "cuda": # cuda on multiple cores is a nightmare for now...
        exit(-1)

    q_model = QModel(FULL_GRID_STATE, H_LAYERS, BOT_ACTIONS, F.leaky_relu)
    if DEVICE == "cuda":
        q_model = q_model.to(torch.device(DEVICE))
        q_model.hidden_units = q_model.hidden_units.to(torch.device(DEVICE))
        for layer in q_model.hidden_units:
            layer = layer.to(torch.device(DEVICE))
    else:
        q_model.share_memory()

    if DEVICE != "cuda":
        processes = []
        print("Training data...")
        detail = DETAILS()
        for rank in range(MAX_PROCESS):
            p = torch.multiprocessing.Process(target=train, args=(q_model,))
            p.start()
            processes.append(p)
        for p in processes:
            detail.update(p.join())
        print_data(detail)

        print("Testing data...")
        detail = DETAILS()
        processes.clear()
        for rank in range(MAX_PROCESS):
            p = torch.multiprocessing.Process(target=test, args=(q_model,))
            p.start()
            processes.append(p)
        for p in processes:
            data = p.join()
            detail.update(data)
        print_data(detail)
    else: # DOESN'T WORK...
        print("Training data...")
        detail = DETAILS()
        torch.multiprocessing.spawn(train, args=(q_model, ), nprocs=MAX_PROCESS, join=False)
        for i in range(MAX_PROCESS):
            data = torch.multiprocessing.SpawnContext.join()
            detail.update(data)
        print_data(detail)

        print("Testing data...")
        detail = DETAILS()
        torch.multiprocessing.spawn(test, args=(q_model, ), nprocs=MAX_PROCESS, join=False)
        for i in range(MAX_PROCESS):
            data = torch.multiprocessing.SpawnContext.join()
            detail.update(data)
        print_data(detail)

if __name__ == '__main__':
    print(DEVICE)
    begin = time()
    # single_run()
    multi_run()
    # test_new()
    end = time()
    print(end-begin)