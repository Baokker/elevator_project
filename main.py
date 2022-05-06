import sys
from enum import Enum  # 枚举类
from functools import partial  # 使button的connect函数可带参数

# pyqt的gui组件
from PyQt5.QtCore import QRect, QThread, QMutex, QTimer
from PyQt5.QtWidgets import QWidget, QPushButton, QApplication, QLabel, QTextEdit, QVBoxLayout, QHBoxLayout, QLCDNumber, \
    QLineEdit

# 窗口大小设置
UI_SIZE = QRect(200, 200, 600, 800)

# 一些全局变量
ELEVATOR_NUM = 5  # 电梯数量
ELEVATOR_FLOORS = 20  # 电梯层数

TIME_PER_FLOOR = 2000  # 运行一间电梯所需时间 单位 毫秒
OPENING_DOOR_TIME = 2000  # 打开一扇门所需时间 单位 毫秒
OPEN_DOOR_TIME = 3000  # 门打开后维持的时间 单位 毫秒


# 电梯的状态 包括正常 开门中 开门 关门中 故障
class ElevatorState(Enum):
    normal = 0
    opening_door = 1
    open_door = 2
    closing_door = 3
    fault = 4
    going_up = 5
    going_down = 6


# 电梯的移动状态 包括静止 向上 向下
class MoveState(Enum):
    up = 2
    down = 3


# 外部按钮产生的任务的分配状态 包括未分配 等待 完成
class OuterTaskState(Enum):
    unassigned = 1
    waiting = 2
    finished = 3


# 描述一个内部数字按下产生的任务
class InnerTask:
    def __init__(self, target):
        self.target = target  # 目标楼层


class OuterTask:
    def __init__(self, target, move_state, state=OuterTaskState.unassigned):  # the task is unfinished by default
        self.target = target  # 目标楼层
        self.move_state = move_state  # 需要的电梯运行方向
        self.state = state  # 是否完成（默认未完成）


# # 内部按钮产生的需求（是一个二维数组）
# inner_requests = []
# 外部按钮产生的需求
outer_requests = []
# 每组电梯的状态
elevator_states = []
# 每台电梯的当前楼层
cur_floor = []
# 每台电梯当前需要向上运行处理的目标有哪些（二维数组，内部仅为数字）
up_targets = []
# 每台电梯当前需要向下运行处理的目标有哪些（二维数组，内部仅为数字）
down_targets = []
# 每台电梯内部的开门/关门键是否被按（True/False）
is_open_button_clicked = []
is_close_button_clicked = []

# 每台电梯当前的运行状态
move_states = []
# 每台电梯开门的进度条 范围为0-1
open_progress = []

# 不能简单地用list的乘法
# 例如 a = [[]] * 5
# a[0].append(1)
# a == [[1],[1],[1],[1],[1]]
# 这是因为后面四个子list 其实只是对第1个list的引用
for qwerty in range(ELEVATOR_NUM):
    # inner_requests.append([])  # add list
    elevator_states.append(ElevatorState.normal)  # 默认正常
    cur_floor.append(1)  # 默认在1楼
    up_targets.append([])
    down_targets.append([])
    is_close_button_clicked.append(False)  # 默认开门关门键没按
    is_open_button_clicked.append(False)
    move_states.append(MoveState.up)  # 默认向上（一开始在1楼 只能向上咯
    open_progress.append(0.0)

# mutex互斥锁
mutex = QMutex()


class Elevator(QThread):
    def __init__(self, elev_id):
        super().__init__()  # 父类构造函数
        self.elev_id = elev_id  # 电梯编号
        self.time_slice = 10  # 时间间隔（单位：毫秒）

    # 移动一层楼
    # 方向由参数确定
    def go_one_floor(self, move_state):
        if move_state == MoveState.up:
            elevator_states[self.elev_id] = ElevatorState.going_up
        elif move_state == MoveState.down:
            elevator_states[self.elev_id] = ElevatorState.going_down

        has_slept_time = 0
        while has_slept_time != TIME_PER_FLOOR:
            # 需要先放开锁 不然别的线程不能运行
            mutex.unlock()
            self.msleep(self.time_slice)
            has_slept_time += self.time_slice
            # 锁回来
            mutex.lock()
            # 如果此时出故障了..
            if elevator_states[self.elev_id] == ElevatorState.fault:
                self.fault_tackle()

        if move_state == MoveState.up:
            cur_floor[self.elev_id] += 1
        elif move_state == MoveState.down:
            cur_floor[self.elev_id] -= 1
        elevator_states[self.elev_id] = ElevatorState.normal
        print(self.elev_id, "号现在在", cur_floor[self.elev_id], "楼")
        if elevator_states[self.elev_id] == ElevatorState.fault:
            self.fault_tackle()

    # 一次门的操作 包括开门和关门
    def door_operation(self):
        opening_time = 0.0
        open_time = 0.0
        elevator_states[self.elev_id] = ElevatorState.opening_door
        while True:
            if elevator_states[self.elev_id] == ElevatorState.fault:
                self.fault_tackle()
                break
            elif is_open_button_clicked[self.elev_id] == True:
                # 门正在关上..
                if elevator_states[self.elev_id] == ElevatorState.closing_door:
                    elevator_states[self.elev_id] = ElevatorState.opening_door

                # 门已经开了，延续开门时间
                if elevator_states[self.elev_id] == ElevatorState.open_door:
                    open_time = 0

                is_open_button_clicked[self.elev_id] = False

            elif is_close_button_clicked[self.elev_id] == True:
                elevator_states[self.elev_id] = ElevatorState.closing_door
                open_time = 0

                is_close_button_clicked[self.elev_id] = False

            # 更新时间
            # 门正在打开
            if elevator_states[self.elev_id] == ElevatorState.opening_door:
                # 需要先放开锁 不然别的线程不能运行
                mutex.unlock()
                self.msleep(self.time_slice)
                opening_time += self.time_slice
                # 锁回来
                mutex.lock()
                open_progress[self.elev_id] = opening_time / OPENING_DOOR_TIME
                if opening_time == OPENING_DOOR_TIME:
                    elevator_states[self.elev_id] = ElevatorState.open_door

            # 门已打开
            elif elevator_states[self.elev_id] == ElevatorState.open_door:
                # 需要先放开锁 不然别的线程不能运行
                mutex.unlock()
                self.msleep(self.time_slice)
                open_time += self.time_slice
                # 锁回来
                mutex.lock()
                if open_time == OPEN_DOOR_TIME:
                    elevator_states[self.elev_id] = ElevatorState.closing_door


            # 门正在关闭
            elif elevator_states[self.elev_id] == ElevatorState.closing_door:
                # 需要先放开锁 不然别的线程不能运行
                mutex.unlock()
                self.msleep(self.time_slice)
                opening_time -= self.time_slice
                # 锁回来
                mutex.lock()
                open_progress[self.elev_id] = opening_time / OPENING_DOOR_TIME
                if opening_time == 0:
                    # 门关好了 润回去咯
                    elevator_states[self.elev_id] = ElevatorState.normal
                    break

    # 当故障发生时 清除原先的所有任务
    def fault_tackle(self):
        elevator_states[self.elev_id] = ElevatorState.fault
        open_progress[self.elev_id] = 0.0
        is_open_button_clicked[self.elev_id] = False
        is_close_button_clicked[self.elev_id] = False
        elevator_states[self.elev_id] = ElevatorState.fault
        for outer_task in outer_requests:
            if outer_task.state == OuterTaskState.waiting:
                if outer_task.target in up_targets[self.elev_id] or outer_task.target in down_targets[self.elev_id]:
                    outer_task.state = OuterTaskState.unassigned  # 把原先分配给它的任务交给handler重新分配
        up_targets[self.elev_id] = []
        down_targets[self.elev_id] = []

    def run(self):
        while True:
            mutex.lock()
            if elevator_states[self.elev_id] == ElevatorState.fault:
                self.fault_tackle()
                mutex.unlock()
                continue

            # 向上扫描状态时
            if move_states[self.elev_id] == MoveState.up:
                if up_targets[self.elev_id] != []:
                    if up_targets[self.elev_id][0] == cur_floor[self.elev_id]:
                        self.door_operation()
                    elif up_targets[self.elev_id][0] > cur_floor[self.elev_id]:
                        self.go_one_floor(MoveState.up)
                        if up_targets[self.elev_id] != [] and up_targets[self.elev_id][0] == cur_floor[self.elev_id]:
                            self.door_operation()
                    # 到达以后 把完成的任务设为true
                    # 内部的任务
                    if up_targets[self.elev_id] != [] and cur_floor[self.elev_id] == up_targets[self.elev_id][0]:
                        up_targets[self.elev_id].pop(0)
                    # 外部按钮的任务
                    for outer_task in outer_requests:
                        if outer_task.target == cur_floor[
                            self.elev_id] and outer_task.move_state == MoveState.up:
                            outer_task.state = OuterTaskState.finished
                # 当没有上行目标而出现下行目标时 更换状态
                elif up_targets[self.elev_id] == [] and down_targets[self.elev_id] != []:
                    move_states[self.elev_id] = MoveState.down



            # 向下扫描状态时
            elif move_states[self.elev_id] == MoveState.down:
                if down_targets[self.elev_id] != []:
                    if down_targets[self.elev_id][0] == cur_floor[self.elev_id]:
                        self.door_operation()
                    elif down_targets[self.elev_id][0] < cur_floor[self.elev_id]:
                        self.go_one_floor(MoveState.down)
                        if down_targets[self.elev_id] != [] and down_targets[self.elev_id][0] == cur_floor[
                            self.elev_id]:
                            self.door_operation()
                    # 将已经完成的任务设为true
                    # 内部的任务
                    if down_targets[self.elev_id] != [] and cur_floor[self.elev_id] == down_targets[self.elev_id][0]:
                        down_targets[self.elev_id].pop(0)
                    # 外部按钮的任务
                    for outer_task in outer_requests:
                        if outer_task.target == cur_floor[self.elev_id] and outer_task.move_state == MoveState.down:
                            outer_task.state = OuterTaskState.finished
                # 当没有下行目标而出现上行目标时 更换状态
                elif down_targets[self.elev_id] == [] and up_targets[self.elev_id] != []:
                    move_states[self.elev_id] = MoveState.up

            mutex.unlock()


class Handler(QThread):
    def __init__(self):
        super().__init__()

    def run(self):
        while True:
            mutex.lock()
            # 不知为何 这里一定要声明一下全局变量..
            global outer_requests

            # handler只处理外面按钮产生的任务安排..
            # 找到距离最短的电梯编号..
            for outer_task in outer_requests:
                if outer_task.state == OuterTaskState.unassigned:  # 如果未分配..
                    min_distance = ELEVATOR_FLOORS + 1
                    target_id = -1
                    for i in range(ELEVATOR_NUM):
                        if elevator_states[i] == ElevatorState.fault:
                            continue
                        # 在相同一层 但是没有在上升 下降 或者故障
                        if cur_floor[i] == outer_task.target and \
                                elevator_states[i] not in [ElevatorState.going_down, ElevatorState.going_up]:
                            target_id = i
                            break
                        # if (move_states[i] == MoveState.up and cur_floor[i] < outer_task.target) or \
                        #         (move_states[i] == MoveState.down and cur_floor[i] > outer_task.target):
                        distance = abs(cur_floor[i] - outer_task.target)
                        if distance < min_distance:
                            min_distance = distance
                            target_id = i

                    # 假如找到了 对应添加任务..
                    if target_id != -1:
                        if cur_floor[target_id] == outer_task.target:
                            if outer_task.move_state == MoveState.up and outer_task.target not in up_targets[
                                target_id]:
                                up_targets[target_id].append(outer_task.target)
                                up_targets[target_id].sort()
                                print(up_targets)
                                # 设为等待态

                                outer_task.state = OuterTaskState.waiting

                            elif outer_task.move_state == MoveState.down and outer_task.target not in down_targets[
                                target_id]:
                                down_targets[target_id].append(outer_task.target)
                                down_targets[target_id].sort(reverse=True)  # 这里需要降序！ 例如，[20,19,..1]
                                print(down_targets)
                                # 设为等待态

                                outer_task.state = OuterTaskState.waiting

                        elif cur_floor[target_id] < outer_task.target and outer_task.target not in up_targets[
                            target_id]:  # up
                            up_targets[target_id].append(outer_task.target)
                            up_targets[target_id].sort()
                            print(up_targets)
                        elif cur_floor[target_id] > outer_task.target and outer_task.target not in down_targets[
                            target_id]:  # down
                            down_targets[target_id].append(outer_task.target)
                            down_targets[target_id].sort(reverse=True)  # 这里需要降序！ 例如，[20,19,..1]
                            print(down_targets)

            # # 再是内部的任务安排..
            # for i in range(ELEVATOR_NUM):
            #     # 假如故障了 跳过..
            #     if elevator_states[i] == ElevatorState.fault:
            #         continue
            #
            #     for inner_task in inner_requests[i]:
            #         if inner_task.state == False:
            #             if cur_floor[i] < inner_task.target and inner_task.target not in up_targets[i]:  # up
            #                 up_targets[i].append(inner_task.target)
            #                 up_targets[i].sort()
            #             elif cur_floor[i] > inner_task.target and inner_task.target not in down_targets[i]:  # down
            #                 down_targets[i].append(inner_task.target)
            #                 down_targets[i].sort(reverse=True)  # 这里需要降序！ 例如，[20,19,..1]
            #
            #     inner_requests[i] = [task for task in inner_requests[i] if task.state == False]

            mutex.unlock()

            mutex.lock()
            # 查看哪些任务已经完成了 移除已经完成的..
            outer_requests = [task for task in outer_requests if task.state != OuterTaskState.finished]
            # for i in range(ELEVATOR_NUM):
            #     inner_requests[i] = [task for task in inner_requests[i] if task.state == False]

            mutex.unlock()


class ElevatorUi(QWidget):
    def __init__(self):
        super().__init__() # 父类构造函数
        self.output = None
        # 各种
        self.__floor_displayers = []
        self.__inner_num_buttons = []
        self.__inner_open_buttons = []
        self.__inner_close_buttons = []
        self.__outer_up_buttons = []
        self.__outer_down_buttons = []
        self.__inner_fault_buttons = []
        self.timer = QTimer()
        self.setup_ui()

    def setup_ui(self):
        self.setWindowTitle("elevator simulator")
        self.setGeometry(UI_SIZE)

        h1 = QHBoxLayout()
        self.setLayout(h1)

        h2 = QHBoxLayout()
        h1.addLayout(h2)

        for i in range(ELEVATOR_NUM):
            v2 = QVBoxLayout()
            h2.addLayout(v2)
            floor_display = QLCDNumber()
            floor_display.setFixedSize(100, 50)
            self.__floor_displayers.append(floor_display)
            v2.addWidget(floor_display)
            self.__inner_num_buttons.append([])
            for j in range(ELEVATOR_FLOORS):
                button = QPushButton(str(ELEVATOR_FLOORS - j))
                button.setFixedSize(100, 25)
                button.clicked.connect(partial(self.__inner_num_button_clicked, i, ELEVATOR_FLOORS - j))
                button.setStyleSheet("background-color : rgb(255,255,255)")
                self.__inner_num_buttons[i].append(button)
                v2.addWidget(button)
            fault_button = QPushButton("故障")
            fault_button.setFixedSize(100, 30)
            fault_button.clicked.connect(partial(self.__inner_fault_button_clicked, i))
            self.__inner_fault_buttons.append(fault_button)
            v2.addWidget(fault_button)
            h3 = QHBoxLayout()
            open_button = QPushButton("开门")
            open_button.setFixedSize(50, 30)
            open_button.clicked.connect(partial(self.__inner_open_button_clicked, i))
            self.__inner_open_buttons.append(open_button)
            close_button = QPushButton("关门")
            close_button.setFixedSize(50, 30)
            close_button.clicked.connect(partial(self.__inner_close_button_clicked, i))
            self.__inner_close_buttons.append(close_button)
            v2.addLayout(h3)
            h3.addWidget(open_button)
            h3.addWidget(close_button)

        v3 = QVBoxLayout()
        h1.addLayout(v3)
        for i in range(ELEVATOR_FLOORS):
            h4 = QHBoxLayout()
            v3.addLayout(h4)
            label = QLabel(str(ELEVATOR_FLOORS - i))
            h4.addWidget(label)
            if i != 0:
                up_button = QPushButton("↑")
                up_button.setFixedSize(30, 30)
                up_button.clicked.connect(
                    partial(self.__outer_direction_button_clicked, ELEVATOR_FLOORS - i, MoveState.up))
                self.__outer_up_buttons.append(up_button)  # 从顶楼往下一楼开始..
                h4.addWidget(up_button)

            if i != ELEVATOR_FLOORS - 1:
                down_button = QPushButton("↓")
                down_button.setFixedSize(30, 30)
                down_button.clicked.connect(
                    partial(self.__outer_direction_button_clicked, ELEVATOR_FLOORS - i, MoveState.down))
                self.__outer_down_buttons.append(down_button)  # 从顶楼开始..到2楼
                h4.addWidget(down_button)

        v1 = QVBoxLayout()
        h1.addLayout(v1)
        label = QLabel("2052329 方必诚\n按下数字键表示电梯将前往该层\n按↑↓键表示此楼有人需要搭乘\n粉色表明该楼需要停靠\n\n输入数字后点击按钮产生任务")
        v1.addWidget(label)

        self.generate_num_edit = QLineEdit()
        self.generate_num_edit.setText("0")
        v1.addWidget(self.generate_num_edit)
        button = QPushButton()
        button.setText("产生任务")
        button.clicked.connect(self.__generate_tasks)
        v1.addWidget(button)
        self.output = QTextEdit()
        self.output.setText("此处输出电梯运转信息：\n")
        v1.addWidget(self.output)

        self.timer.setInterval(30)

        self.timer.timeout.connect(self.update)

        self.timer.start()

        self.show()

    def __generate_tasks(self):
        import random
        for i in range(int(self.generate_num_edit.text())):
            if random.randint(0, 100) < 30:  # 30% 产生外部任务
                rand = random.randint(1, ELEVATOR_FLOORS)
                if rand == 1:  # 1楼只能向上
                    self.__outer_direction_button_clicked(1, MoveState.up)
                elif rand == ELEVATOR_FLOORS:  # 顶楼只能向下
                    self.__outer_direction_button_clicked(rand, MoveState.down)
                else:
                    self.__outer_direction_button_clicked(rand, random.choice([MoveState.up, MoveState.down]))
            else:  # 产生内部任务
                self.__inner_num_button_clicked(random.randint(0, ELEVATOR_NUM - 1), random.randint(1, ELEVATOR_FLOORS))

    def __inner_open_button_clicked(self, elevator_id):
        mutex.lock()
        if elevator_states[elevator_id] == ElevatorState.fault:
            self.output.append(str(elevator_id) + "号电梯出现故障 正在维修!")
            mutex.unlock()
            return

        if elevator_states[elevator_id] == ElevatorState.closing_door or elevator_states[
            elevator_id] == ElevatorState.open_door:
            is_open_button_clicked[elevator_id] = True
            is_close_button_clicked[elevator_id] = False

        self.__inner_open_buttons[elevator_id].setStyleSheet("background-color : yellow")
        self.output.append(str(elevator_id) + "电梯开门!")
        mutex.unlock()

    def __inner_close_button_clicked(self, elevator_id):
        mutex.lock()
        if elevator_states[elevator_id] == ElevatorState.fault:
            self.output.append(str(elevator_id) + "号电梯出现故障 正在维修!")
            mutex.unlock()
            return

        if elevator_states[elevator_id] == ElevatorState.opening_door or elevator_states[
            elevator_id] == ElevatorState.open_door:
            is_close_button_clicked[elevator_id] = True
            is_open_button_clicked[elevator_id] = False

        self.__inner_close_buttons[elevator_id].setStyleSheet("background-color : yellow")
        self.output.append(str(elevator_id) + "电梯关门!")
        mutex.unlock()

    def __inner_fault_button_clicked(self, elevator_id):
        mutex.lock()
        if elevator_states[elevator_id] != ElevatorState.fault:
            elevator_states[elevator_id] = ElevatorState.fault

            self.__inner_fault_buttons[elevator_id].setStyleSheet("background-color : yellow")
            for button in self.__inner_num_buttons[elevator_id]:
                button.setStyleSheet("background-color : rgb(255,255,255)")
            self.__inner_open_buttons[elevator_id].setStyleSheet("background-color : None")
            self.__inner_close_buttons[elevator_id].setStyleSheet("background-color : None")

            self.output.append(str(elevator_id) + "电梯故障!")


        else:
            elevator_states[elevator_id] = ElevatorState.normal

            self.__inner_fault_buttons[elevator_id].setStyleSheet("background-color : None")
            self.output.append(str(elevator_id) + "电梯正常!")

        mutex.unlock()

    def __inner_num_button_clicked(self, elevator_id, floor):
        mutex.lock()

        if elevator_states[elevator_id] == ElevatorState.fault:
            self.output.append(str(elevator_id) + "号电梯出现故障 正在维修!")
            mutex.unlock()
            return

        # 相同楼层不处理
        if floor == cur_floor[elevator_id]:
            mutex.unlock()
            return

        task = InnerTask(floor)
        if elevator_states[elevator_id] != ElevatorState.fault:
            if task.target > cur_floor[elevator_id] and task.target not in up_targets[elevator_id]:
                up_targets[elevator_id].append(task.target)
                up_targets[elevator_id].sort()
            elif task.target < cur_floor[elevator_id] and task.target not in down_targets[elevator_id]:
                down_targets[elevator_id].append(task.target)
                down_targets[elevator_id].sort(reverse=True)

            self.__inner_num_buttons[elevator_id][ELEVATOR_FLOORS - floor].setStyleSheet("background-color : yellow")
            self.output.append(str(elevator_id) + "号电梯" + "的用户请求前往" + str(floor) + "楼!")

        mutex.unlock()

    def __outer_direction_button_clicked(self, floor, move_state):
        mutex.lock()

        task = OuterTask(floor, move_state)

        if task not in outer_requests:
            outer_requests.append(task)

            if move_state == MoveState.up:
                self.__outer_up_buttons[ELEVATOR_FLOORS - floor - 1].setStyleSheet("background-color : yellow")
            elif move_states == MoveState.down:
                self.__outer_down_buttons[ELEVATOR_FLOORS - floor].setStyleSheet("background-color : yellow")

            self.output.append(str(floor) + "的用户上下楼请求!")

        mutex.unlock()

    def update(self):
        mutex.lock()
        for i in range(ELEVATOR_NUM):
            self.__floor_displayers[i].display(cur_floor[i])
            if not is_open_button_clicked[i]:
                self.__inner_open_buttons[i].setStyleSheet("background-color : None")

            if not is_close_button_clicked[i]:
                self.__inner_close_buttons[i].setStyleSheet("background-color : None")

            # 对内部的按钮，如果在开门或关门状态的话，则设进度条
            if elevator_states[i] in [ElevatorState.opening_door, ElevatorState.open_door, ElevatorState.closing_door]:
                self.__inner_num_buttons[i][ELEVATOR_FLOORS - cur_floor[i]].setStyleSheet(
                    "background-color : rgb(255," + str(int(255 * (1 - open_progress[i]))) + ",255)")

        mutex.unlock()
        # 对外部来说，遍历任务，找出未完成的设为红色，其他设为默认none
        for button in self.__outer_up_buttons:
            button.setStyleSheet("background-color : None")

        for button in self.__outer_down_buttons:
            button.setStyleSheet("background-color : None")

        mutex.lock()
        for outer_task in outer_requests:
            if outer_task.state != OuterTaskState.finished:
                if outer_task.move_state == MoveState.up:
                    self.__outer_up_buttons[ELEVATOR_FLOORS - outer_task.target - 1].setStyleSheet(
                        "background-color : pink")
                elif outer_task.move_state == MoveState.down:
                    self.__outer_down_buttons[ELEVATOR_FLOORS - outer_task.target].setStyleSheet(
                        "background-color : pink")

        mutex.unlock()


if __name__ == '__main__':
    app = QApplication(sys.argv)

    # 开启线程
    handler = Handler()
    handler.start()

    elevators = []
    for i in range(ELEVATOR_NUM):
        elevators.append(Elevator(i))

    for elevator in elevators:
        elevator.start()

    e = ElevatorUi()
    sys.exit(app.exec_())
