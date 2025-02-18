#!/usr/bin/env python3
import cmath
import copy as copy
import rclpy
import cv2
import numpy as np
from rclpy.node import Node
from std_msgs.msg import Int16MultiArray, Float32
from geometry_msgs.msg import Vector3, Twist
from sensor_msgs.msg import Image
from cv_bridge import CvBridge
from std_msgs.msg import Bool
class MinimalSubscriber(Node):

    def __init__(self):
        super().__init__('minimal_subscriber')
        self.subscription = self.create_subscription(
            Int16MultiArray(),
            '/positions_balles',
            self.listener_callback,
            10)
        self.subscription  # prevent unused variable warning

        self.subscription2 = self.create_subscription(
            Vector3,
            '/position_robot',
            self.listener_pos_rob_callback,
            10)
        self.subscription2  # prevent unused variable warning

        self.subscription3 = self.create_subscription(
            Float32,
            '/orientation_robot',
            self.listener_orientation_callback,
            10)
        self.subscription3  # prevent unused variable warning
        self.subscription4 = self.create_subscription(
            Image,
            '/zenith_camera/image_raw',
            self.detect_zone,
            10)
        self.publisher_ = self.create_publisher(Twist, '/demo/cmd_vel', 10)
        self.publisher1_ = self.create_publisher(Bool, '/bool_pelle', 10)
        timer_period = 0.1  # seconds
        self.timer = self.create_timer(timer_period, self.timer_cmd_callback)

        self.position_robot = (0, 0)
        self.orientation_robot = 0
        self.cmd_linear = Vector3()  # must be a Vector3
        self.cmd_angular = Vector3()  # must be a Vector3
        # TODO find the correct coordinates
        self.coords_zone = [[100, 100], [100, 100]]
        self.coords_entry = [[121, 121], [100, 100]]
        self.coords_net = [[-100, 0], [100, 0]]
        self.net_sides = [[[0, 0], [0, 0]], [[0, 0], [0, 0]]]
        self.lis_balls = []
        self.waypoints = []
        self.err_prec = 0.
        self.ball_is_catch = True



    def detect_zone(self, msg):
        
        current_frame = CvBridge().imgmsg_to_cv2(msg)
        current_frame = cv2.cvtColor(current_frame, cv2.COLOR_BGR2RGB)
        hsv = cv2.cvtColor(current_frame, cv2.COLOR_RGB2HSV)
        # on effectue un masque avec les valeurs ci-dessous recuperee sur internet
        # pour ne garder que les lignes jaunes
        lower = np.array([100, 40, 90], dtype=np.uint8)
        upper = np.array([110, 255, 255], dtype=np.uint8)
        seg0 = cv2.inRange(hsv, lower, upper)
        kernel = np.ones((5, 5), np.uint8)
        seg0 = cv2.morphologyEx(seg0, cv2.MORPH_OPEN, kernel)
        # cv2.imshow("test", seg0)
        # cv2.waitKey(1)
        coord_x, coord_y = np.array(np.where(seg0 == 255))
        # print("pixels des safe zones : ", np.array([coord_x, coord_y]))
        safe_l_x, safe_l_y = [], []
        safe_r_x, safe_r_y = [], []
        for i in range(len(coord_y)):
            if coord_y[i] <= 650:
                safe_l_x.append(coord_x[i])
                safe_l_y.append(coord_y[i])
            else:
                safe_r_x.append(coord_x[i])
                safe_r_y.append(coord_y[i])
        safe_l_x, safe_l_y = np.array(safe_l_x), np.array(safe_l_y)
        safe_r_x, safe_r_y = np.array(safe_r_x), np.array(safe_r_y)
        coord_l_center = [np.mean(safe_l_x), np.mean(safe_l_y)]
        coord_r_center = [np.mean(safe_r_x), np.mean(safe_r_y)]
        coord_l_entry = [np.max(safe_l_x), np.max(safe_l_y)]
        coord_r_entry = [np.min(safe_r_x), np.min(safe_r_y)]
        self.coords_zone = [coord_l_center, coord_r_center]
        self.coords_entry = [coord_l_entry, coord_r_entry]

    def timer_cmd_callback(self):
        msg = Twist()
        msg.linear = self.cmd_linear
        msg.angular = self.cmd_angular      
        ### A REVOIR NE MARCHE PAS BIEN
        if len(self.waypoints) <5 and self.position_robot != (0,0):
            self.ajout_waypoint() # possiblement à mettre en dehors
        if self.waypoints != [] and self.position_robot!= (0,0):
            dest_x, dest_y = self.waypoints[0][0], self.waypoints[0][1]
            self.straight_line(dest_x, dest_y)
        ###
        self.publisher_.publish(msg)
        b = Bool()
        (x,y) = self.position_robot
        (c1,c2)= self.waypoints[0]
        d = np.sqrt((x-c1)**2+(y-c2)**2)
        if d<100:
            b.data = False
            self.publisher1_.publish(b)
        else : 
            b.data = True
            self.publisher1_.publish(b)
            
    def ball_is_catch(self):
        """Cette fonction permet de savoir si le waypoint atteint correspond à une balle attrapée"""
        points_filets = [(70,590), (70,690), (630,690), (630,590)]
        if self.waypoints[0,0] not in points_filets:
            self.ball_is_catch = True
            
    def listener_callback(self, msg):
        lis_interm = []
        for i in range(0, len(msg.data), 3):
            lis_interm.append([msg.data[i], msg.data[i + 1], msg.data[i + 2]])
        self.lis_balls = lis_interm
        

    def listener_pos_rob_callback(self, msg):
        pos_x = msg.x
        pos_y = msg.y
        self.position_robot = (pos_x, pos_y)
        self.get_logger().info(str(self.position_robot))


    def listener_orientation_callback(self, msg):
        self.orientation_robot = msg.data


    def angle(self, pos_1, pos_2):
        vect = np.array([[pos_2[0]-pos_1[0]], [pos_2[1]-pos_1[1]]])
        angle = np.arccos(vect[0, 0]/np.linalg.norm(vect))
        if pos_2[1]<pos_1[1]:
            angle = -angle
        return angle


    def straight_line(self, x_dest=500, y_dest=300):
        """
        Robot goes in a straight line to the desired position.

        input : coordinates of the robot and coordinates to go
        output : None, the robot goes to the desired position
        """
        x, y = self.position_robot
        angle_robot = self.orientation_robot
        #vect_theta = np.array([[x_dest - x], [y_dest - y]])
        theta = self.angle((x,y), (x_dest, y_dest))

        err_angle =0.05  # rad
        err_pos_imp = 100
        err_pos_imp2 = 40
        err_pos = 20 #pixel
        vit_rot = 0.5
        kp = 0.2
        #self.get_logger().info('angle cherché: "%f"' % theta) 
        #self.get_logger().info('angle actu: "%f"' % angle_robot) 

        self.get_logger().info(str(self.position_robot)+ "pos_rob")
        self.get_logger().info(str(x_dest)+ " " + str(y_dest))
        err = theta - angle_robot

        if (abs(x - x_dest)>=err_pos or abs(y - y_dest)>=err_pos):
            if (np.abs(theta - angle_robot) > err_angle):
                if (abs(x - x_dest)>=err_pos or abs(y - y_dest)>=err_pos):
                    if (abs(x - x_dest)>=err_pos_imp and abs(y - y_dest)>=err_pos_imp):
                        self.cmd_linear.x = 0.7
                    elif (abs(x - x_dest)>=err_pos_imp2 and abs(y - y_dest)>=err_pos_imp2):
                        self.cmd_linear.x = 0.4
                    else: 
                        self.cmd_linear.x = 0.
                    if np.sign(theta) == np.sign(angle_robot):
                        if theta > angle_robot:
                            self.cmd_angular.z = vit_rot*np.abs(theta - angle_robot)/2 + kp*(err - self.err_prec)
                        else:
                            self.cmd_angular.z = -vit_rot*np.abs(theta - angle_robot)/2 + kp*(err - self.err_prec)
                    else:
                        if np.abs(theta - angle_robot) > np.pi:
                            if theta < angle_robot:
                                self.cmd_angular.z = vit_rot*(np.abs(theta - angle_robot)-np.pi)/2 + kp*(err - self.err_prec)
                            else:
                                self.cmd_angular.z = -vit_rot*(np.abs(theta - angle_robot)-np.pi)/2 + kp*(err - self.err_prec)
                        else:
                            if theta < angle_robot:
                                self.cmd_angular.z = -vit_rot*np.abs(theta - angle_robot)/2 + kp*(err - self.err_prec)
                            else:
                                self.cmd_angular.z = vit_rot*np.abs(theta - angle_robot)/2 + kp*(err - self.err_prec)
            else:

                self.cmd_angular.z = 0.
                if (abs(x - x_dest)>=err_pos*2 or abs(y - y_dest)>=err_pos*2):
                   self.cmd_linear.x = 0.7
                if ( err_pos<abs(x - x_dest)<err_pos*2 or err_pos<abs(y - y_dest)<err_pos*2):
                    self.cmd_linear.x = 0.4

                
        else:
            self.waypoints.remove(self.waypoints[0])
            self.get_logger().info(str("waypoint atteint"))
            self.cmd_linear.x = 0.

        self.err_prec = err


    def ajout_waypoint(self):
        """Cette fonction permet d'ajouter ou de modifier les waypoints que doit suivre le robot, elle va modifier self.waypoints mais ne rien renvoyer."""
        # A REVOIR, NE MARCHE PAS BIEN
        if self.ball_is_catch:
            x, y = self.position_robot
            if y < 640:
                self.waypoints = [(self.coords_zone[0][0], self.coords_zone[0][1])]
            else:
                self.waypoints = [(self.coords_zone[1][0], self.coords_zone[1][1])]

        if self.lis_balls != [] and self.ball_is_catch == False:
            lis_balls = copy.deepcopy(self.lis_balls)
            ramassage_balle = self.path_balls(lis_balls, lis_balls[0], self.position_robot[0], self.position_robot[1], 5)
            # if self.in_square(self.position_robot) == self.in_square(lis_balls[0]):
            #     ramassage_balle = self.path_balls(lis_balls, lis_balls[0], self.position_robot[0], self.position_robot[1], 30)
            #     self.get_logger().info("ON est dans le même carré")
            # else:
            #     ramassage_balle = self.path_balls(lis_balls, self.passage_filet("near"), self.position_robot[0], self.position_robot[1], 30) + self.path_balls(lis_balls, self.passage_filet("far"), self.passage_filet("near")[0], self.passage_filet("near")[0], 30) + self.path_balls(lis_balls, lis_balls[0], self.passage_filet("far")[0], self.passage_filet("far")[1], 30)
            #     self.get_logger().info("On doit passer le filet")
            #self.get_logger().info("Ramasse"+str(ramassage_balle))
            #self.get_logger().info("waypoint"+str(self.waypoints))
            self.waypoints = ramassage_balle




    def passage_filet(self):
        """
        Cette fonction renvoie la position du point au niveau du filet par lequel le robot doit passer pour changer de côté.

        Returns
        -------
            tuple(int,int): le point sur le côté du filet par lequel le robot doit passer.
        
        """
        x = self.position_robot[0]
        y = self.position_robot[1]
        vert = "haut"
        hor = "droite"

        if x >= 360:
            vert = "bas"
        if y <= 640:
            hor = "gauche"

        if vert == "haut":
            if hor == "gauche" and dist=="near":
                return (70, 590)
            elif hor == "gauche" and dist=="far":
                return (70, 690)
            elif hor == "droite" and dist=="near":
                return (70, 690)
            elif hor == "droite" and dist=="far":
                return (70, 590)
        else:
            if hor == "gauche" and dist=="near":
                return (630, 590)
            elif hor == "gauche" and dist=="far":
                return (630, 690)
            elif hor == "droite" and dist=="near":
                return (630, 690)
            elif hor == "droite" and dist=="far":
                return (630, 590)


    def min_distance(self, x, y, list_coords):
        """
        Cette fonction renvoie la distance minimal d'un point (x,y) à une liste de points.

        Input : x and y coordinates, a list of coordinates.
        list_coords = [[x0, y0], [x1, y1], ....]
        output : x and y coordinates in list_coords for which 
        the distance is minimal
        """
        d = []
        for c in list_coords:
            d.append([np.sqrt((c[0] - x)**2+(c[1] - y)**2), c])

        d.sort()
        return d[0][1][0], d[0][1][1]


    def oldest(self, ball):
        """
        Cette fonction renvoie le temps d'une balle.

        Input: ball [x,y,time].
        output: time
        """
        return ball[2]


    def path_balls(self, lis_balls, ball_obj, x_robot, y_robot, radius=5):
        # Careful ! lis_balls will be modified, therefore must not be the original one, 
        # rather a copy
        """
        Determine the path for a robot, given a destination ball, in order to grab as many balls as possible in the way.

        Args:
        ----
            lis_balls (int[3][]): list of the balls that could be in the trajectory of the robot
            ball_obj (int[3]): the destination ball that will be reached eventually
            x_robot (int): x coordinate of the robot
            y_robot (int): y coordinate of the robot
            radius (float): opening of the way. The bigger it is, the more likely the robot is to find a ball to grab in the way.
        
        Returns
        -------
            int[2][]: the list of the coordinates of the balls that can be grabbed in the way
        
        """
        path = [(ball_obj[0], ball_obj[1])]
        for ball in lis_balls:
            if self.ball_in_traj(ball, x_robot, y_robot, ball_obj[0], ball_obj[1], radius):
                lis_balls.remove(ball)
                path = self.path_balls(lis_balls, ball, x_robot, y_robot, 0.75 * radius) + \
                    self.path_balls(lis_balls, ball_obj,
                                    ball[0], ball[1], 0.75 * radius)
                break
        return path


    def ball_in_traj(self, ball, x_robot, y_robot, x_dest, y_dest, radius):
        """
        Check wether a ball ball is within a rectangle formed by the segment between robot and dist and with a width 2 * radius.

        Args
        ----
            ball (int[3]): the coordinates and the order of the ball
            x_robot (int): x coordinate of the robot
            y_robot (int): y coordinate of the robot
            x_dest (int): x coordinate of the objective ball
            y_dest (int): y coordinate of the objective ball
            radius (float): the semi-width of the rectangle

        Returns
        -------
            bool: whether the ball is in the rectangle or not

        """
        complex_vect = complex(x_dest - x_robot, y_dest - x_dest)

        angle = np.angle(complex_vect)#[0]
        corners = [(x_robot + radius * np.sin(angle), y_robot - radius * np.cos(angle)),
                    (x_robot - radius * np.sin(angle), y_robot + radius * np.cos(angle)),
                    (x_dest - radius * np.sin(angle), y_dest + radius * np.cos(angle)),
                    (x_dest + radius * np.sin(angle), y_dest - radius * np.cos(angle))]  
                    # 4 corners of the rectangle, turning clockwise
        bottom_right, bottom_left, top_left, top_right = corners
        coefs_first_vert_line_0 = (bottom_left[1] - top_left[1])/(bottom_left[0] - top_left[0])
        coefs_first_vert_line_1 = bottom_left[1] - coefs_first_vert_line_0 * bottom_left[0]
        coefs_first_vert_line = (coefs_first_vert_line_0, coefs_first_vert_line_1)
        coefs_second_vert_line_0 = (bottom_right[1] - top_right[1])/(bottom_right[0] - top_right[0])
        coefs_second_vert_line_1 = bottom_right[1] - coefs_first_vert_line_0 * bottom_right[0]
        coefs_second_vert_line = (coefs_second_vert_line_0, coefs_second_vert_line_1)
        coefs_first_horiz_line_0 = (bottom_left[1] - bottom_right[1])/(bottom_left[0] - bottom_right[0])
        coefs_first_horiz_line_1 = bottom_left[1] - coefs_first_horiz_line_0 * bottom_left[0]
        coefs_first_horiz_line = (coefs_first_horiz_line_0, coefs_first_horiz_line_1)
        coefs_second_horiz_line_0 = (top_right[1] - top_left[1]) / (top_right[0] - top_left[0])
        coefs_second_horiz_line_1 = top_right[1] - coefs_first_horiz_line_0 * top_right[0]
        coefs_second_horiz_line = (coefs_second_horiz_line_0, coefs_second_horiz_line_1)
        if (ball[1] > coefs_first_vert_line[0] * ball[0] + coefs_first_vert_line[1] and
            ball[1] < coefs_second_vert_line[0] * ball[0] + coefs_second_vert_line[1])\
            or (ball[1] < coefs_first_vert_line[0] * ball[0] + coefs_first_vert_line[1] and
            ball[1] > coefs_second_vert_line[0] * ball[0] + coefs_second_vert_line[1]):
            if (ball[1] > coefs_first_horiz_line[0] * ball[0] + coefs_first_horiz_line[1] and
                ball[1] < coefs_second_horiz_line[0] * ball[0] + coefs_second_horiz_line[1])\
                or (ball[1] < coefs_first_horiz_line[0] * ball[0] + coefs_first_horiz_line[1] and
                ball[1] > coefs_second_horiz_line[0] * ball[0] + coefs_second_horiz_line[1]):
                return True
        return False


    def in_square(self, coords):
        """
        Cette fonction indique si le robot est sur la gauche ou la droite du filet.
        
        Input: coordinates [x,y].
        output: Side of the net, "Left" or "Right"
        """
        #left = [self.net_sides[0][0][0], self.net_sides[0][1][0]]
        #right = [self.net_sides[1][0][0], self.net_sides[1][1][0]]

        #if min(left) <= coords[0] <= max(left):
        #    return 'Left'
        #elif min(right) <= coords[0] <= max(right):
        #    return 'Right'
        if coords[1] <= 640:    
            return 'Left'
        else:
            return 'Right'


    def ball_to_fetch(self, ball_list, radius, objective='zone'):
        """
        Cette fonction renvoie une liste de balle à attraper.

        Input : list of balls with coordinates and time falling, a radius to search around,
        the objective.
        structure of ball_list : [[x,y,time], ...]
        objective can be "zone" or "ball"
        output : list of balls to fectch between the robot and the objective
        """
        x_robot, y_robot = self.position_robot  # fetch the robot coordinates
        x_dest, y_dest = 0, 0

        if objective == 'zone':
            x_dest, y_dest = self.min_distance(x_robot, y_robot, self.coords_zone)
        elif objective == 'ball':
            ball_list.sort(key=self.oldest)

            x_dest, y_dest = ball_list[0][0], ball_list[0][1]
        else:
            return print('Please enter a correct objective')

        ball_to_fetch = []
        for b in ball_list:
            if (self.ball_in_traj(b, x_robot, y_robot, x_dest, y_dest, radius)):
                ball_to_fetch.append([b[0], b[1]])

        return ball_to_fetch


    def goto(self, x_robot, y_robot, x_dest, y_dest):
        """
        Pas utilisée.

        Input : coordinates of the robot and coordinates to go.
        output : None, the robot goes to the desired position
        """
        if (self.in_square([x_robot, y_robot]) == self.in_square([x_dest, y_dest])):
            print('Robot is in the same side than the ball')
            self.straight_line(x_robot, y_robot, x_dest, y_dest)

        else:
            print('Robot need to change side')
            x_mid, y_mid = self.min_distance(x_robot, y_robot, self.coords_net)
            self.straight_line(x_robot, y_robot, x_mid, y_mid)
            self.straight_line(x_mid, y_mid, x_dest, y_dest)


def main(args=None):
    rclpy.init(args=args)

    minimal_subscriber = MinimalSubscriber()

    rclpy.spin(minimal_subscriber)
    minimal_subscriber.straight_line(10, 10)

    # Destroy the node explicitly
    # (optional - otherwise it will be done automatically
    # when the garbage collector destroys the node object)
    minimal_subscriber.destroy_node()
    rclpy.shutdown()


if __name__ == '__main__':
    main()
