import tensorflow as tf
import numpy as np
from Duel_DDQN import Exp



# Evaluates behavior policy while improving target policy
class duel_DDQN_agent():
    '''
    Args:
        - num_actions: number of actions possible
        - obs_size: size of the state/observation. size of image
        - nhidden: hidden nodes for network
        - epoch: variable that helps know when to do experience replay and training (through modulo)
        - epsilon: epsilon decay, exploration vs exploitation
        - gamma: TODO: var used in dueling? used as discount factor
        - learning_rate: for gradient descent network training
        - replace: can be 'soft' or 'hard'. different types of replacement. 
        - polyak: var used in soft replacement formula. how much to update in soft replacement
        - tau_step: hard replacement var. Used to know when to do replacement
        - mem_size: max memory used for exp replay buffer
        - minibatch_size: minibatch for training size
    '''
    def __init__(self, num_actions, obs_size, nhidden, epoch, 
                 epsilon, gamma, learning_rate, replace, polyak, 
                 tau_step, mem_size, minibatch_size):

        super(duel_DDQN_agent, self).__init__()
        
        self.actions = range(num_actions)
        self.num_actions = num_actions
        self.obs_size = obs_size # number of features
        self.nhidden = nhidden # hidden nodes
        
        # for epsilon decay & to decide when to start training
        # used in epsilon decay function for modulo to know when to decay
        self.epoch = epoch 

        self.epsilon = epsilon # for exploration
        self.gamma = gamma # discount factor
        self.learning_rate = learning_rate # learning rate alpha
        
        # for params replacement
        self.replace = replace # type of replacement
        self.polyak = polyak # for soft replacement
        self.tau_step = tau_step # for hard replacement
        self.learn_step = 0 # steps after learning # count of hard replacement
        
        # for Experience replay
        self.mem = Exp(self.obs_size, mem_size) # memory that holds experiences
        self.minibatch_size = minibatch_size
        
        self.step = 0 # each step in a episode. Increment after taking 1 action. 
                
        # for tensorflow ops
        self.built_graph() # call function that builds tf graph and sets up network        
        # TODO: this is deprecated but there is tuto on how to migrate to tf 2
        self.sess = tf.Session() 
        self.sess.run(tf.global_variables_initializer())
        self.sess.run(self.target_replace_hard)
        
        self.cum_loss_per_episode = 0 # incremented loss for charting display
        
    # decay epsilon after each epoch    
    def epsilon_decay(self):
        if self.step % self.epoch == 0:
            # TODO: make decay rate a var in __init__
            self.epsilon = max(.01, self.epsilon * .95)
            
    
    # TODO: stopped here
    # epsilon-greedy behaviour policy for action selection   
    def act(self, s):
        # Get action either randomly or from network
        if np.random.random() < self.epsilon:
            i = np.random.randint(0,len(self.actions))
        else: 
            # get Q(s,a) from model network
            # TODO: change self.sess
            Q_val = self.sess.run(self.model_Q_val, feed_dict={self.s: np.reshape(s, (1, s.shape[0]))})
            # get index of largest Q(s,a)
            i = np.argmax(Q_val)
            
        action = self.actions[i]   
        
        self.step += 1 
        self.epsilon_decay()
        
        return action     
    
    def learn(self, s, a, r, done):
        # stores observation in memory as experience at each time step 
        # self.mem is class object from experience_replay
        self.mem.store(s, a, r, done)
        # starts training a minibatch from experience after 1st epoch
        if self.step > self.epoch:
            self.replay() # start training with experience replay

    def td_target(self, s_next, r, done, model_s_next_Q_val, target_Q_val):  
        # This function does Bellman update and is used to calculate loss of network
        # select action with largest Q value from model network
        model_max_a = tf.argmax(model_s_next_Q_val, axis=1, output_type=tf.dtypes.int32)
        
        arr = tf.range(tf.shape(model_max_a)[0], dtype=tf.int32) # create row indices    
        indices = tf.stack([arr, model_max_a], axis=1) # create 2D indices        
        max_target_Q_val = tf.gather_nd(target_Q_val, indices) # select minibatch actions from target network       
        max_target_Q_val = tf.reshape(max_target_Q_val, (self.minibatch_size,1))
        
        # if state = done, td_target = r
        # Bellman update
        td_target = (1.0 - tf.cast(done, tf.float32)) * tf.math.multiply(self.gamma, max_target_Q_val) + r
        # exclude td_target in gradient computation
        td_target = tf.stop_gradient(td_target)

        return td_target
      
    # select Q(s,a) from actions using e-greedy as behaviour policy from model network
    def predicted_Q_val(self, a, model_Q_val):        
        # create 1D tensor of length = number of rows in a
        arr = tf.range(tf.shape(a)[0], dtype=tf.int32)
        
        # stack by column to create indices for Q(s,a) selections based on a
        indices = tf.stack([arr, a], axis=1)
        
        # select Q(s,a) using indice from model_Q_val
        Q_val = tf.gather_nd(model_Q_val, indices)
        Q_val = tf.reshape(Q_val, (self.minibatch_size,1))
        
        return Q_val

    # contruct neural network
    def built_net(self, var_scope, w_init, b_init, features, num_hidden, num_output):       
        # TODO: change contrib to tf2 fns     
        model = tf.keras.Sequential()  
        input_layer = tf.keras.Input(shape=(self.obs_size,))
        feature_layer = tf.keras.layers.Dense(num_hidden, activation = 'relu' )
        V = tf.keras.layers.Dense(1)
        A = tf.keras.layers.Dense(num_output)
        # with tf.variable_scope(var_scope):       
        #     feature_layer = tf.keras.layers.Dense(features, num_hidden, 
        #                                           activation = 'relu',
        #                                           weights_initializer = w_init,
        #                                           biases_initializer = b_init)   
        #   feature_layer = tf.contrib.layers.fully_connected(features, num_hidden, 
        #                                                     activation_fn = tf.nn.relu,
        #                                                     weights_initializer = w_init,
        #                                                     biases_initializer = b_init)
        #   V = tf.contrib.layers.fully_connected(feature_layer, 1, 
        #                                         activation_fn = None,
        #                                         weights_initializer = w_init,
        #                                         biases_initializer = b_init) 
        #   A = tf.contrib.layers.fully_connected(feature_layer, num_output, 
        #                                         activation_fn = None,
        #                                         weights_initializer = w_init,
        #                                         biases_initializer = b_init)   
          Q_val = V + (A - tf.reduce_mean(A, reduction_indices=1, keepdims=True)) # refer to eqn 9 from the original paper          
        return Q_val    
      
    # contruct tensorflow graph
    def built_graph(self):              
        tf.reset_default_graph()
        

        # Initialize all variables
        self.s = tf.placeholder(tf.float32, [None, self.obs_size], name='s')
        self.a = tf.placeholder(tf.int32, [None,], name='a')
        self.r = tf.placeholder(tf.float32, [None,1], name='r')
        self.s_next = tf.placeholder(tf.float32, [None,self.obs_size], name='s_next')
        self.done = tf.placeholder(tf.int32, [None,1], name='done') 
        self.model_s_next_Q_val = tf.placeholder(tf.float32, [None,self.num_actions], name='model_s_next_Q_val')
        
        # weight, bias initialization
        w_init = tf.initializers.lecun_uniform()
        b_init = tf.initializers.he_uniform(1e-4)
        
        self.model_Q_val = self.built_net('model_net', w_init, b_init, self.s, self.nhidden, self.num_actions)
        self.target_Q_val = self.built_net('target_net', w_init, b_init, self.s_next, self.nhidden, self.num_actions)         
          
        # TODO: change variable_scope to tf2 fns
        with tf.variable_scope('td_target'):
          td_target = self.td_target(self.s_next, self.r, self.done, self.model_s_next_Q_val, self.target_Q_val)
        with tf.variable_scope('predicted_Q_val'):
          predicted_Q_val = self.predicted_Q_val(self.a, self.model_Q_val)
        with tf.variable_scope('loss'):
          self.loss = tf.losses.huber_loss(td_target, predicted_Q_val)
        with tf.variable_scope('optimizer'):
          self.optimizer = tf.train.GradientDescentOptimizer(self.learning_rate).minimize(self.loss)
          
        # get network params  
        with tf.variable_scope('params'):
          self.target_net_params = tf.get_collection(tf.GraphKeys.GLOBAL_VARIABLES, scope='target_net')
          self.model_net_params = tf.get_collection(tf.GraphKeys.GLOBAL_VARIABLES, scope='model_net')  
        
        # replace target net params with model net params
        with tf.variable_scope('hard_replace'):
          self.target_replace_hard = [t.assign(m) for t, m in zip(self.target_net_params, self.model_net_params)]
        with tf.variable_scope('soft_replace'):            
          self.target_replace_soft = [t.assign(self.polyak * m + (1 - self.polyak) * t) for t, m in zip(self.target_net_params, self.model_net_params)]                
              
    # decide soft or hard params replacement        
    def replace_params(self):
        if self.replace == 'soft':
            # Move weights partially: 0.9 target + 0.1 model
            # soft params replacement 
            self.sess.run(self.target_replace_soft)  
        else:
            # copy weight from trained to target every tau steps
            # hard params replacement
            if self.learn_step % self.tau_step == 0:
                self.sess.run(self.target_replace_hard)  
            self.learn_step += 1
                
    def replay(self):             
        # select minibatch of experiences from memory for training
        (s, a, r, s_next, done) = self.mem.minibatch(self.minibatch_size)
        
        # select actions from model network
        model_s_next_Q_val = self.sess.run(self.model_Q_val, feed_dict={self.s: s_next})

        # training
        _, loss = self.sess.run([self.optimizer, self.loss], 
                                feed_dict = {self.s: s,
                                self.a: a,
                                self.r: r,
                                self.s_next: s_next,
                                self.done: done,
                                self.model_s_next_Q_val: model_s_next_Q_val})  
        self.cum_loss_per_episode += loss
        self.replace_params()      