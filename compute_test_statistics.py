# Import required libraries
import numpy as np
from sklearn.linear_model import LinearRegression
from sklearn.linear_model import Lasso
from collections import namedtuple
from sklearn.preprocessing import PolynomialFeatures
import scipy.sparse as sp
from scipy.stats import multivariate_normal
from copy import copy
from sklearn.kernel_approximation import RBFSampler
# from sklearn.metrics import pairwise_distances
from scipy.spatial.distance import pdist
from joblib import Parallel, delayed
from bisect import bisect_right
import csv
import warnings
warnings.filterwarnings("error")



# %% create polynomial features without interaction terms
class PolynomialFeatures_no_interaction():
    def __init__(self, degree, include_bias):
        self.degree = degree
        self.include_bias = include_bias

    def fit_transform(self, X):
        new_X = np.hstack([X ** (i + 1) for i in range(self.degree)])
        if self.include_bias:
            new_X = np.hstack([np.ones(shape=(new_X.shape[0],1)), new_X])
        return new_X


# %% fitted Q iteration
class q_learning():
    """
    Q Function approximation via polynomial regression.
    """
    def __init__(self, States, Rewards, Actions, qmodel='rbf', degree=2, gamma=0.95,
                 rbf_bw=1.0, poly_interaction=False, RBFSampler_random_state = 1):
        '''
        initialization
        :param env: an object of RLenv
        :param degree: degree of polynomial basis used for functional approximation of Q function
        :param gamma: discount rate of rewards
        :param time_start: starting time of the interval
        :param time_terminal: terminal time of the interval
        '''

        # self.env = env
        # degree of polynomial basis
        self.degree = degree
        # initial_dsgn = self.create_design_matrix_t(self.featurize_state(initial_states), self.env.Actions[:, time_start])
        # self.model = LinearRegression(fit_intercept = False)#SGDRegressor(learning_rate="constant")
        # self.model = KernelRidge(kernel='rbf')#SGDRegressor(learning_rate="constant")
        self.qmodel = qmodel

        # if no rbf basis, then just a linear term
        if degree == 0 and qmodel == 'rbf':
            self.qmodel = 'polynomial'
            self.degree = 1

        if self.qmodel == "rbf":
            self.featurize = RBFSampler(gamma=rbf_bw, random_state=RBFSampler_random_state, n_components=degree)
            self.model = LinearRegression(fit_intercept=False)
        elif self.qmodel == "polynomial":
            if poly_interaction:
                self.featurize = PolynomialFeatures(degree=self.degree, include_bias=True)#(degree != 1) *
            else: # exclude interactions
                self.featurize = PolynomialFeatures_no_interaction(degree=self.degree, include_bias=True)
            self.model = LinearRegression(fit_intercept=False)
        else:
            pass

        # # get initial states
        # initial_states = np.vstack(States[:, 0, :])
        # # number of features
        # self.p = len(self.featurize_state([initial_states[0, :]])[0])
        self.States = States
        self.Rewards = Rewards
        self.Actions = Actions
        # number of unique actions
        self.n_actions = len(np.unique(Actions))

        # self.model.fit(initial_dsgn, env.Rewards[:, time_start])
        # self.theta = self.model.coef_

        # self.theta = np.zeros(self.p * env.nAction)
        # self.time_start = time_start
        # self.time_terminal = time_terminal
        self.gamma = gamma
        self.N = Actions.shape[0]
        self.T = Actions.shape[1]

        # create design matrix for the current states
        # print(self.featurize)
        self.States0 = self.create_design_matrix(States, Actions, type='current', pseudo_actions=None)
        ## create design matrix for the next states
        self.States1_action0 = self.create_design_matrix(States, Actions, type='next', pseudo_actions=0)
        self.States1_action1 = self.create_design_matrix(States, Actions, type='next', pseudo_actions=1)

        # create vector of rewards
        self.Rewards_vec = Rewards.flatten()

        # # number of features in the design matrix for (s,a)
        # self.p = int(self.States0.shape[1] / self.n_actions)
        # print("self.States0 =", self.States0[0:5,:].toarray())
        # print("RBFSampler_random_state =", RBFSampler_random_state)

    def featurize_state(self, state):
        """
        Returns the transformed representation for a state.
        """

        if self.qmodel == "polynomial":
            return self.featurize.fit_transform(state)
        elif self.qmodel == "rbf":
            out = self.featurize.fit_transform(state)
            # add intercept
            return PolynomialFeatures(degree=1, include_bias=True).fit_transform(out)
        else: # do nothing
            pass

    def create_sp_design_matrix(self, features, Actions):
        """
        Create a sparse design matrix phi for functional approximation.
        For each action a in the action space, the features phi(States, a) is a Nxp matrix.
        phi is composed of combining the columns of phi(States, a), depending on the action taken
        :return: an np.array of size N x (p*a)
        """
        p = features.shape[1]
        ## create column indices for the sparse matrix
        idx_add = p * np.arange(self.n_actions)
        col = np.array([xi + np.arange(p) for xi in idx_add])
        col_idx = col[Actions]
        col_idx = np.concatenate(col_idx)

        ## create row indices for the sparse matrix
        row_idx = np.repeat(np.arange(features.shape[0]), p)

        # creating sparse matrix
        sparseMatrix = sp.csr_matrix((np.concatenate(features), (row_idx, col_idx)),
                                     shape=(features.shape[0], p * self.n_actions))
        return sparseMatrix


    def create_design_matrix(self, States, Actions, type='current', pseudo_actions=None):
        '''
        Create design matrix of States from time t0 to t1 (both inclusive)
        :param type: 'current' for St or 'next' for S_t+1
        :param pseudo_actions:
        :param return_list:
        :return:
        '''
        if type == 'current':
            # stack the states by person, and time: S11, ..., S1T, S21, ..., S2T
            States_stack = States[:, :-1 or None, :].transpose(2, 0, 1).reshape(States.shape[2], -1).T
            Actions_stack = Actions.flatten()
        elif type == 'next':
            States_stack = States[:, 1:, :].transpose(2, 0, 1).reshape(States.shape[2], -1).T
            if pseudo_actions is not None:
                Actions_stack = np.repeat(pseudo_actions, States_stack.shape[0])
            else:
                Actions_stack = Actions.flatten()

        features = self.featurize_state(States_stack)

        return self.create_sp_design_matrix(features, Actions_stack)



    def fit(self, model=None, max_iter=200, tol=1e-6):
        # initialize error and number of iterations
        err = 1.0
        num_iter = 0

        # initialize parameter theta
        if model is None:
            if self.qmodel == "rbf" or self.qmodel == "polynomial":
                self.model = LinearRegression(fit_intercept = False)
                self.model.fit(self.States0, self.Rewards_vec)
        else:
            self.model = model
            # is the model initialized?
            try:
                self.model.coef_
            except: # if not initialized
                self.model.fit(self.States0, self.Rewards_vec)


        ## FQI
        convergence = True
        errors = []
        loss = []
        while err > tol and num_iter <= max_iter:
            model_old = copy(self.model)

            # estimated Q value at the current time
            # Q_old = model.predict(States0)
            # Q0 = States0 @ theta

            # predict the Q value for the next time and find out the maximum Q values for each episode
            Q_max = np.asarray([self.model.predict(self.States1_action0),
                                self.model.predict(self.States1_action1)]).max(0)

            # compute TD target
            td_target = self.Rewards_vec + self.gamma * Q_max

            # update parameter fit
            self.model.fit(self.States0, td_target)

            # model = FQI_one_iter(model)
            predicted = self.model.predict(self.States0)
            err = np.sqrt(sum(model_old.predict(self.States0) - predicted) ** 2)
            errors.append(err)

            # least square loss
            loss.append(np.mean( (td_target - predicted)**2 ))
            num_iter += 1

            # break if exceeds the max number of iterations allowed
            if num_iter > max_iter:
                convergence = False
                break

        ## calculate TD error
        Q_predict = np.asarray([self.model.predict(self.States1_action0),
                                self.model.predict(self.States1_action1)])
        td_error = self.Rewards_vec + self.gamma * Q_predict.max(0) - self.model.predict(self.States0)

        ## calculate W matrix
        # obtain the optimal actions at S_t+1
        optimal_Actions = Q_predict.argmax(0)

        # create design matrix for the states under the optimal actions
        optimal_design_matrix = self.create_design_matrix(self.States, optimal_Actions, 'next')
        # print("optimal_Actions =", optimal_Actions[0:10])
        # print("optimal_design_matrix =", optimal_design_matrix.toarray()[0:10,:])
        W_mat = self.States0.T.dot(self.States0 - self.gamma * optimal_design_matrix) / self.T
        try:
            FQI_result = namedtuple("beta", ["beta", "W_mat", "design_matrix", 'td_error', 'Qmodel'])
            return FQI_result(self.model.coef_, W_mat, self.States0, td_error, [errors, num_iter, convergence, loss])
        except:
            FQI_result = namedtuple("beta", ["W_mat", "design_matrix", 'td_error', 'Qmodel'])
            return FQI_result(W_mat, self.States0, td_error, [errors, num_iter, convergence, loss])


    def optimal(self):
        Actions0 = np.zeros(self.Actions.shape, dtype='int32')
        design_matrix0 = self.create_design_matrix(self.States, Actions0, type='current', pseudo_actions=None)
        q_estimated0 = self.model.predict(design_matrix0)

        Actions0 = np.ones(self.Actions.shape, dtype='int32')
        design_matrix0 = self.create_design_matrix(self.States, Actions0, type='current', pseudo_actions=None)
        q_estimated1 = self.model.predict(design_matrix0)

        opt_reward = np.maximum(q_estimated0, q_estimated1)
        opt_action = np.argmax(np.vstack((q_estimated0, q_estimated1)), axis=0)
        optimal = namedtuple("optimal", ["opt_reward", "opt_action"])
        return optimal(opt_reward, opt_action)


    def predict(self, States):
        N = States.shape[0]
        T = States.shape[1] - 1
        Actions0 = np.zeros(shape=(N,T), dtype='int32')
        design_matrix0 = self.create_design_matrix(States, Actions0, type='current', pseudo_actions=None)
        q_estimated0 = self.model.predict(design_matrix0)

        Actions0 = np.ones(shape=(N,T), dtype='int32')
        design_matrix0 = self.create_design_matrix(States, Actions0, type='current', pseudo_actions=None)
        q_estimated1 = self.model.predict(design_matrix0)
        # print("q_estimated0 =", q_estimated0)
        # print("q_estimated1 =", q_estimated1)
        opt_reward = np.maximum(q_estimated0, q_estimated1)
        opt_action = np.argmax(np.vstack((q_estimated0, q_estimated1)), axis=0)
        optimal = namedtuple("optimal", ["opt_reward", "opt_action"])
        return optimal(opt_reward, opt_action)

#%%
def split_train_test(n, fold = 5):
    '''
    split data into n-fold training and test data
    :param n: sample size of the original data
    :param fold: integer, number of folds
    :return: a list of nfold elements, each element is a list of indices
    '''
    seq = np.random.permutation(n)
    """Yield n number of sequential chunks from seq."""
    d, r = divmod(n, fold)
    for i in range(fold):
        si = (d + 1) * (i if i < r else r) + d * (0 if i < r else i - r)
        yield seq[si:si + (d + 1 if i < r else d)]

def gaussian_rbf_distance(x1, x2, bandwidth = 1.0):
    return np.exp(- bandwidth * np.sum((x1 - x2)  ** 2))

def train_test(States, Rewards, Actions, test_index, num_basis, u, bandwidth = 1.0,
          qmodel='rbf', gamma=0.95, model=None, max_iter=300, tol=1e-2, criterion = 'ls', RBFSampler_random_state=1):

    #%% training
    # extract training data
    States_train = np.delete(States, (test_index), axis=0)
    Rewards_train = np.delete(Rewards, (test_index), axis=0)
    Actions_train = np.delete(Actions, (test_index), axis=0)
    q1 = q_learning(States_train[:, :(u + 1), :], Rewards_train[:, :u], Actions_train[:, :u], qmodel, num_basis, gamma, num_basis, bandwidth, RBFSampler_random_state=RBFSampler_random_state)
    q2 = q_learning(States_train[:, u:, :], Rewards_train[:, u:], Actions_train[:, u:], qmodel, num_basis, gamma, num_basis, bandwidth, RBFSampler_random_state=RBFSampler_random_state)
    # States1 = q1.States0
    States1_action0 = q1.States1_action0
    States1_action1 = q1.States1_action1
    # States2 = q2.States0
    States2_action0 = q2.States1_action0
    States2_action1 = q2.States1_action1
    design_matrix = sp.vstack(( sp.hstack((q1.States0, sp.csr_matrix(q1.States0.shape))),
                                sp.hstack((sp.csr_matrix(q2.States0.shape), q2.States0)) ))
    design_matrix_action0 = sp.vstack((sp.hstack((States1_action0, sp.csr_matrix(States1_action0.shape))),
                                       sp.hstack((sp.csr_matrix(States2_action0.shape), States2_action0))))
    design_matrix_action1 = sp.vstack((sp.hstack((States1_action1, sp.csr_matrix(States1_action1.shape))),
                                       sp.hstack((sp.csr_matrix(States2_action1.shape), States2_action1))))

    # create vector of rewards
    # Rewards_vec = Rewards_test.flatten()
    Rewards_vec = np.hstack((q1.Rewards_vec, q2.Rewards_vec))

    # initialize error and number of iterations
    err = 1.0
    num_iter = 0

    # initialize parameter theta
    if model is None:
        if qmodel == "polynomial" or qmodel == "rbf":
            model = LinearRegression(fit_intercept=False)
        model.fit(design_matrix, Rewards_vec)
    else:
        # is the model initialized?
        try:
            model.coef_
        except:  # if not initialized
            model.fit(design_matrix, Rewards_vec)


    ## FQI
    convergence = True
    # errors = []
    # loss = []
    while err > tol and num_iter <= max_iter:
        model_old = copy(model)

        # estimated Q value at the current time
        # Q_old = model.predict(States0)
        # Q0 = States0 @ theta
        try:

            # predict the Q value for the next time and find out the maximum Q values for each episode
            Q_max = np.asarray([model.predict(design_matrix_action0),
                                model.predict(design_matrix_action1)]).max(0)

            # compute TD target
            td_target = Rewards_vec + gamma * Q_max

            # update parameter fit
            model.fit(design_matrix, td_target)

            # model = FQI_one_iter(model)
            predicted = model.predict(design_matrix)

            # temporal difference error
            # tde =
            err = np.sqrt(sum(model_old.predict(design_matrix) - predicted) ** 2)
        except RuntimeWarning:
            print("In CV training, matrix is not invertible in regression")
        num_iter += 1

        # break if exceeds the max number of iterations allowed
        if num_iter > max_iter:
            convergence = False
            break

    del States_train, Rewards_train, Actions_train

    if not convergence:  # if converged:
        print("FQI did not converge")
        if max(abs(model.coef_)) > 1e10:
            loss = 1e10
            return loss

    # %% testing
    # extract training data
    States_test = States[test_index, :, :]
    Rewards_test = Rewards[test_index, :]
    Actions_test = Actions[test_index, :]

    q1 = q_learning(States_test[:, :(u + 1), :], Rewards_test[:, :u], Actions_test[:, :u], qmodel, num_basis,
                    gamma, num_basis, bandwidth, RBFSampler_random_state=RBFSampler_random_state)
    q2 = q_learning(States_test[:, u:, :], Rewards_test[:, u:], Actions_test[:, u:], qmodel, num_basis, gamma,
                    num_basis, bandwidth, RBFSampler_random_state=RBFSampler_random_state)
    States1_action0 = q1.States1_action0
    States1_action1 = q1.States1_action1
    States2_action0 = q2.States1_action0
    States2_action1 = q2.States1_action1
    design_matrix = sp.vstack((sp.hstack((q1.States0, sp.csr_matrix(q1.States0.shape))),
                               sp.hstack((sp.csr_matrix(q2.States0.shape), q2.States0))))
    design_matrix_action0 = sp.vstack((sp.hstack((States1_action0, sp.csr_matrix(States1_action0.shape))),
                                       sp.hstack((sp.csr_matrix(States2_action0.shape), States2_action0))))
    design_matrix_action1 = sp.vstack((sp.hstack((States1_action1, sp.csr_matrix(States1_action1.shape))),
                                       sp.hstack((sp.csr_matrix(States2_action1.shape), States2_action1))))

    # create vector of rewards
    # Rewards_vec = Rewards_test.flatten()
    Rewards_vec = np.hstack((q1.Rewards_vec, q2.Rewards_vec))

    # predict the Q value for the next time and find out the maximum Q values for each episode
    Q_max = np.asarray([model.predict(design_matrix_action0),
                        model.predict(design_matrix_action1)]).max(0)
    # temporal difference error
    tde = Rewards_vec + gamma * Q_max - model.predict(design_matrix)
    del design_matrix, design_matrix_action0, design_matrix_action1

    # calculate loss depending on convergence criterion
    if criterion == 'ls': # least squares
        loss = np.mean(tde ** 2)
    elif criterion == 'kerneldist': # kernel distance
        def distance_function_state(x1,x2):
            return gaussian_rbf_distance(x1, x2, bandwidth)
        def distance_function_action(x1,x2):
            return abs(x1 - x2)
        def tde_product(x1, x2):
            return x1 * x2

        # first piece
        States_stack = States_test[:, :u, :].transpose(2, 0, 1).reshape(States.shape[2], -1).T
        nrow1 = States_stack.shape[0]
        Actions_vec = Actions_test[:, :u].flatten()
        K_states = pdist(States_stack, metric=distance_function_state)
        K_actions = pdist(Actions_vec.reshape(-1, 1), metric=distance_function_action)
        tdes = pdist(tde[:States_stack.shape[0]].reshape(-1, 1), metric=tde_product)
        K_total = np.sum((1.0 + K_actions + K_states + K_actions * K_states) * tdes)
        # second piece
        tdes = pdist(tde[States_stack.shape[0]:].reshape(-1, 1), metric=tde_product)
        States_stack = States_test[:, u:-1, :].transpose(2, 0, 1).reshape(States.shape[2], -1).T
        nrow2 = States_stack.shape[0]
        Actions_vec = Actions_test[:, u:].flatten()
        K_states = pdist(States_stack, metric=distance_function_state)
        K_actions = pdist(Actions_vec.reshape(-1, 1), metric=distance_function_action)
        K_total += np.sum((1.0 + K_actions + K_states + K_actions * K_states) * tdes)
        loss = K_total / ((nrow1 * (nrow1 - 1) / 2) + (nrow2 * (nrow2 - 1) / 2))
    return loss




def select_num_basis_cv(States, Rewards, Actions, u, num_basis_list=[0,1,2,3], bandwidth = 1.0,
                        qmodel='rbf', gamma=0.95, model=None, max_iter=300, tol=1e-4,
                        nfold = 5, num_threads = 5, criterion = 'ls', seed=0, RBFSampler_random_state=1):
    np.random.seed(seed)
    N = Rewards.shape[0]
    test_indices = list(split_train_test(N, nfold))
    # random_states = np.random.randint(np.iinfo(np.int32).max, size=n_vectors)

    T = Rewards.shape[1]
    if N*T*States.shape[2] > 100000:
        num_threads = 1
    else:
        num_threads = 5

    min_test_error = 500.0
    selected_num_basis = num_basis_list[0]
    for num_basis in num_basis_list:

        def run_one(fold):
            return train_test(States, Rewards, Actions, test_indices[fold], num_basis, u,
                                 bandwidth, qmodel, gamma, model, max_iter, tol, criterion, RBFSampler_random_state)

        # parallel jobs
        test_errors = Parallel(n_jobs=num_threads, prefer="threads")(delayed(run_one)(fold) for fold in range(nfold))
        test_error = np.mean(test_errors)
        print(test_error)

        # get the mse of the least square loss in the last iteration
        if test_error < min_test_error:
            min_test_error = test_error
            selected_num_basis = num_basis

    # find the minimum mse
    basis = namedtuple("basis", ["num_basis", "test_error"])
    return basis(selected_num_basis, test_error)




#%%
def evaluation(States, Rewards, Actions, T_total,
           qmodel = 'rbf', degree=4, rbf_bw = 1.0,
           gamma=0.95, num_threads=1,
           theta=0.5, J=10, epsilon=0.02, 
           select_basis = False, select_basis_interval = 10, num_basis_list=[1,2,3],
           criterion = 'ls', seed = 0, RBFSampler_random_state = 1,
           changepoint = 0):
    np.random.seed(seed)

    ## get dimensions
    N = Actions.shape[0]
    T = Actions.shape[1]
    p_state = States.shape[2]
    n_actions = len(np.unique(Actions))

    # calculate the range of u
    # create a list of candidate change points

    if N > 100:  # if sample size is too large
        sample_subject_index = np.random.choice(N, 100, replace=False)
    else:
        sample_subject_index = np.arange(N)
    ### compute bandwidth if not input
    if rbf_bw is None:
        # compute pairwise distance between states for the first piece
        pw_dist = pdist(States[sample_subject_index, :, :].transpose(2, 0, 1).reshape(p_state, -1).T,
                                     metric='euclidean')
        rbf_bw = 1.0 / np.nanmedian(np.where(pw_dist > 0, pw_dist, np.nan))
        # use the median of the minimum of distances as bandwidth
        # rbf_bw = np.median(np.where(pw_dist > 0, pw_dist, np.inf).min(axis=0))
        print("Bandwidth chosen: {:.5f}".format(rbf_bw))
        del pw_dist

    # get a list of u at which basis selection will be performed
    if select_basis:  # if we perform basis selection:
        basis = select_num_basis_cv(States[sample_subject_index, :, :],
                                        Rewards[sample_subject_index, :],
                                        Actions[sample_subject_index, :], u, num_basis_list, rbf_bw,
                                        qmodel, gamma, model=None, max_iter=400, tol=1e-4, nfold=5,
                                        num_threads=num_threads*5, criterion=criterion, seed=seed,
                                        RBFSampler_random_state=RBFSampler_random_state)
        degree = basis.num_basis
        
        fqi_model = q_learning(States[:,0:(u+1),:], Rewards[:,0:u], Actions[:,0:u], qmodel, degree, gamma, rbf_bw,
                        RBFSampler_random_state=RBFSampler_random_state)
        # model = copy(fqi_model.model)
        # # model = Lasso(alpha=0.001, fit_intercept=False, max_iter=400)
        # # initialize model parameters with 0 responses
        # model.fit(fqi_model.States0, fqi_model.Rewards_vec)
    else: # if we do not perform basis selection, then use the default for both pieces
        fqi_model = q_learning(States[:,0:(u+1),:], Rewards[:,0:u], Actions[:,0:u], qmodel, degree, gamma, rbf_bw,
                RBFSampler_random_state=RBFSampler_random_state)
        # model = copy(fqi_model.model)
        # # model = Lasso(alpha=0.001, fit_intercept=False, max_iter=400)
        # # initialize model parameters with 0 responses
        # model.fit(fqi_model.States0, fqi_model.Rewards_vec)
    
    return