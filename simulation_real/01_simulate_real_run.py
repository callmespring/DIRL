'''
Simulate nonstationary time series data and apply Q-learning.
Data generation mechanism resembles the IHS data
'''
#!/usr/bin/python
import platform, sys, os, pickle
plat = platform.platform()
print(plat)
if plat == 'macOS-12.5-x86_64-i386-64bit': ##local
    os.chdir("/Users/mengbing/Documents/research/change_point_clustering/HeterRL_private/simulation_real")
    sys.path.append("/Users/mengbing/Documents/research/change_point_clustering/HeterRL_private")
elif plat == 'Linux-3.10.0-1160.42.2.el7.x86_64-x86_64-with-centos-7.6.1810-Core': # biostat cluster
    os.chdir("/home/mengbing/research/HeterRL/simulation_real")
    sys.path.append("/home/mengbing/research/HeterRL")
elif plat == 'Linux-4.18.0-305.45.1.el8_4.x86_64-x86_64-with-glibc2.28':  # greatlakes
    os.chdir("/home/mengbing/research/HeterRL/simulation_real")
    sys.path.append("/home/mengbing/research/HeterRL")

import numpy as np
import matplotlib.pyplot as plt
from datetime import datetime
# import simu.simu_mean_detect_modified as mean_detect
import simu.simu_mean_detect as mean_detect
from sklearn.metrics.cluster import adjusted_rand_score
import simulation_real.simulate_data_real as sim
import copy
# import pandas as pd
from simu.utilities import *
# from sklearn.tree import DecisionTreeRegressor
# from sklearn import tree
from functions.evaluation_separateA import *
# import HeterRL.functions.compute_test_statistics_separateA as stat


# Arguments passed

# # argv should be: seed, kappa, degree, num_threads
seed = int(sys.argv[1])
effect_size = str(sys.argv[2])
K = int(sys.argv[3])
init = int(sys.argv[4])
# # threshold_type = str(sys.argv[3]) #"Chi2" or "permutation"
# seed = 20
# effect_size = "strong"
# K = 3
# init = 20

# import importlib
# importlib.reload(sim)
# importlib.reload(mean_detect)

startTime = datetime.now()
np.random.seed(seed)
print("seed =", seed)

# %% simulate data
# terminal timestamp
T = 26
#change point
# change_pt = 16
# number of people
# N = int(3)
N_per_cluster = 50
num_threads = 5
test_setting = "cdist"
# effect_size = "large"
if effect_size == "weak":
    effect_size_factor = 0.2
elif effect_size == "moderate":
    effect_size_factor = 0.5
elif effect_size == "strong":
    effect_size_factor = 0.8
base_transition = np.array([[10, 0.4, -0.04, 0.1],
                            [11, -0.4, 0.05, 0.4],
                            [1.2, -0.02, 0.03, 0.8]])
cluster_settings = {'cluster1': {'n': N_per_cluster, 'changepoints': [11],
                                 'state': [base_transition +
                                           np.zeros(shape = (3,4)) * effect_size_factor,
                                           ]*2,
                                 'action': [np.array([[0.6, 0.3, 0, 0],
                                                     [-0.4, 0, 0, 0],
                                                     [-0.5, 0, 0, 0]])*effect_size_factor,
                                            np.array([[0.6, 0.3, 0, 0],
                                                      [-0.4, 0, 0, 0],
                                                      [-0.5, 0, 0, 0]])*-1.0*effect_size_factor
                                            ]
                                 },
                    'cluster2': {'n': N_per_cluster, 'changepoints': [9, 17],
                                 'state': [base_transition +
                                           np.array([[-1.0, 0.0, 0, 0],
                                                    [-0.5, 0.0, 0.0, 0.0],
                                                    [-0.2, 0, 0.0, 0.0]]) * effect_size_factor,
                                           base_transition +
                                           np.array([[1.0, 0.15, -0.01, 0.02],
                                                     [1.0, -0.15, 0.01, 0.1],
                                                     [0.3, -0.01, 0.01, -0.15]]) * effect_size_factor,
                                           base_transition +
                                           np.array([[1.0, 0.15, -0.01, 0.02],
                                                     [1.0, -0.15, 0.01, 0.1],
                                                     [0.3, -0.01, 0.01, -0.15]]) * effect_size_factor
                                           ],
                                 'action': [np.array([[0.5, 0.3, 0, 0],
                                                     [-0.3, 0, 0, 0],
                                                     [-0.4, 0, 0, 0]])*effect_size_factor,
                                            np.array([[0.7, 0.2, 0, 0],
                                                      [-0.5, 0, 0, 0],
                                                      [-0.6, 0, 0, 0]])*-1.0*effect_size_factor,
                                            np.array([[0.7, 0.2, 0, 0],
                                                      [-0.5, 0, 0, 0],
                                                      [-0.6, 0, 0, 0]])*effect_size_factor
                                            ]
                                 },
                    'cluster3': {'n': N_per_cluster, 'changepoints': [26],
                                 'state': [base_transition +
                                           np.array([[1.5, 0.05, 0, 0],
                                                     [0.5, -0.2, 0.0, 0.0],
                                                     [0.2, 0, 0.0, 0.0]]) * effect_size_factor
                                           ]*2,
                                 'action': [np.array([[0.55, 0.25, 0, 0],
                                                     [-0.4, 0, 0, 0],
                                                     [-0.5, 0, 0, 0]])*effect_size_factor]*2
                                 }
                    }

# importlib.reload(sim)
sim_dat = sim.simulate_data(T, cluster_settings)
States, Rewards, Actions = sim_dat.simulate(seed, burnin=60)

# make a copy
States_s = copy(States)
# dimension of States
p_var = 3
def transform(x):
    return (x - np.mean(x)) / np.std(x)
for i in range(p_var):
    States_s[:,:,i] = transform(States[:,:,i])

# number of clusters
K_true = len(cluster_settings)
N = sim_dat.N


# %% evaluation function
def evaluate(changepoints_true, g_index, predict, T):
    '''
    g_index : predicted group index
    predict : predicted changepoints
    '''
    changepoint_err = np.mean(np.abs(predict - changepoints_true)/T)
    cluster_err = adjusted_rand_score(g_index_true, g_index)
    return changepoint_err, cluster_err

#%% storage path setup
# test_setting = "cdist"
# method = 'proposed'
# create folder under seed if not existing
path_name = 'data/'
if not os.path.exists(path_name):
    os.makedirs(path_name, exist_ok=True)
path_name += '20221031_C0/'
if not os.path.exists(path_name):
    os.makedirs(path_name, exist_ok=True)
path_name += "sim_" + effect_size + "/"
if not os.path.exists(path_name):
    os.makedirs(path_name, exist_ok=True)
# path_name += "init" + str(init) + "/"
# if not os.path.exists(path_name):
#     os.makedirs(path_name, exist_ok=True)

# direct the screen output to a file
stdoutOrigin = sys.stdout
sys.stdout = open(path_name + "log_seed" + str(seed) + "_K" + str(K) + "_init" + str(init) + ".txt", "w")
print("\nName of Python script:", sys.argv[0])
sys.stdout.flush()

changepoints_true = np.repeat([11,17,0], [N_per_cluster]*3, axis=0)
g_index_true = np.repeat([0,1,2], [N_per_cluster]*3, axis=0)


#%% simu0: KMeans clustering + multiple random change points
from tslearn.clustering import TimeSeriesKMeans

# K_list = [3]
# g_index_init_list = [g_index_true]
# number of random initial changepoints
epsilon = 0.05
# n_init_cp = 3
best_model_IC = -1e9
best_model = None
nthread = 5
threshold_type = "maxcusum"
max_iter = 10
B = 5000
kappa_min = int((T - 1 - np.max(changepoints_true)) * 0.8)
kappa_max = min(T - 1, int((T - 1 - np.min(changepoints_true)) * 1.2))


# %% init with a fixed change point
changepoints_init = np.repeat(init, N)
out = mean_detect.fit(States_s, Actions, example="cdist", seed=seed, K=K, C = 0,
                      init="changepoints", changepoints_init=changepoints_init, B=B,
                      epsilon=epsilon, nthread=nthread, threshold_type=threshold_type,
                      kappa_min=kappa_min, kappa_max=kappa_max,
                      max_iter=max_iter, is_cp_parallel = 1)


# %%
changepoint_err, ARI = evaluate(changepoints_true.squeeze(), out[1].squeeze(), out[2].squeeze(), T)
print('changepoint_err', changepoint_err, 'ARI', ARI)


saved_data = {
    "model_IC": out[4][0],
    "loss": out[3],
    'K': K,
    "changepoints": out[2].squeeze(),
    "changepoint_err": changepoint_err,
    "clusters": out[1].squeeze(),
    "cluster_ari": ARI,
    "iter_num": out[0] + 1
    }
file_name = path_name + "result_seed" + str(seed) + "_K" + str(K) + "_init" + str(init) + ".dat"
# file_name = path_name + "cpresult_" + "seed" + str(seed) + ".dat"
with open(file_name, 'wb') as f:
    pickle.dump(saved_data, f)

print("Clusters:", out[1].squeeze())
print("Changepoints:", out[2].squeeze())

sys.stdout.close()
sys.stdout=stdoutOrigin

# #%% init random clustering with K_list
# setting = "initrandom_selectK"
# print(setting)
# K_list = range(2, 6)
# # out = mean_detect.fit(States_s, Actions, example=test_setting, C3=1.0, init="changepoints",
# #                       K=K, threshold_type="permutation", B = 1000,
# #                       seed=seed, nthread=num_threads, max_iter=15)
# g_index_init_list = [np.random.choice(range(K), size=N) for K in K_list]
# g_index_init_list[K_list.index(3)] = None
# out = mean_detect.fit_tuneK(K_list, States, Actions, init="clustering", example="cdist",
#                             seed=seed, nthread=num_threads, max_iter=5,
#                             C=1.0, changepoints_init=None, g_index_init_list=g_index_init_list,
#                             clustering_warm_start=0, distance_metric="euclidean")
#
# changepoint_err, cluster_err = evaluate_Klist(K_list, out, changepoints_true, N, T)
# print('cp:', changepoint_err)
# print('ari:', cluster_err)
#
# model_IC = [0,0,0,0,0,0,out[2][6]]
# save_data = {
#     "model": model_IC,
#     'K_best': out[0],
#     "changepoints": out[2][2].flatten(),
#     "changepoint_err": changepoint_err,
#     "cluster_err": cluster_err,
#     "iter_num": out[2][0] + 1}
# file_name = path_name + "seed" + str(seed) + "_" + setting + "_cpresult" + ".dat"
# # file_name = path_name + "cpresult_" + "seed" + str(seed) + ".dat"
# with open(file_name, 'wb') as f:
#     pickle.dump(save_data, f)
#
# print("Clusters:", out[2][1])
# print("Changepoints:", out[2][2].flatten())
#
#
#
# #%% simu1: init changepoint separatly + K=3
# K=3
# setting = "initseparately"
# print(setting)
# out = mean_detect.fit(States_s, Actions, example=test_setting, C3=1.0, init="changepoints",
#                       K=K, threshold_type="permutation", B = 1000,
#                       seed=seed, nthread=num_threads, max_iter=15)
# changepoint_err, cluster_err = evaluate(changepoints_true.squeeze(), out[1].squeeze(), out[2].squeeze(), N, T)
# print('cp:', changepoint_err)
# print('ari:', cluster_err)
#
# iter_num = out[0] + 1
# save_data = {
#     "model": out,
#     "changepoints": out[2],
#     "changepoint_err": changepoint_err,
#     "cluster_err": cluster_err,
#     "iter_num": iter_num}
# file_name = path_name + "seed" + str(seed) + "_" + setting + "_cpresult" + ".dat"
# with open(file_name, 'wb') as f:
#     pickle.dump(save_data, f)
# print("Clusters:", out[1])
# print("Changepoints:", out[2].flatten())
#
#
#
# #%% simu2: init changepoint non-informatively
# settings = ["initnoninformative", "initrandom"]
# for setting in settings:
#     print(setting)
#     if setting == "initnoninformative":
#         changepoints_init = np.zeros([N, 1])
#     elif setting == "initrandom":
#         changepoints_init = np.random.choice(range(T - 1), size=N)
#     out = mean_detect.fit(States_s, Actions, example=test_setting, changepoints_init=changepoints_init, C3=1.0, init="changepoints",
#                           K=K, threshold_type="permutation", B = 1000,
#                           seed=seed, nthread=num_threads, max_iter=15)
#     changepoint_err, cluster_err = evaluate(changepoints_true.squeeze(), out[1].squeeze(), out[2].squeeze(), N, T)
#     print('cp:', changepoint_err)
#     print('ari:', cluster_err)
#
#     iter_num = out[0] + 1
#     save_data = {
#         "model": out,
#         "changepoints": out[2],
#         "changepoint_err": changepoint_err,
#         "cluster_err": cluster_err,
#         "iter_num": iter_num}
#     file_name = path_name + "seed" + str(seed) + "_" + setting + "_cpresult" + ".dat"
#     with open(file_name, 'wb') as f:
#         pickle.dump(save_data, f)
#     print("Clusters:", out[1])
#     print("Changepoints:", out[2].flatten())
#
#
# #%% simu3: init consistent clustering with K = 3
# setting = "initKmeans"
# print(setting)
# out = mean_detect.fit(States_s, Actions, example=test_setting, C3=1.0, init="clustering",
#                       K=K, threshold_type="permutation", B = 1000, distance_metric="euclidean",
#                       seed=seed, nthread=num_threads, max_iter=15)
# changepoint_err, cluster_err = evaluate(changepoints_true.squeeze(), out[1].squeeze(), out[2].squeeze(), N, T)
# print('cp:', changepoint_err)
# print('ari:', cluster_err)
#
# iter_num = out[0] + 1
# save_data = {
#     "model": out,
#     "changepoints": out[2],
#     "changepoint_err": changepoint_err,
#     "cluster_err": cluster_err,
#     "iter_num": iter_num}
# file_name = path_name + "seed" + str(seed) + "_" + setting + "_cpresult" + ".dat"
# with open(file_name, 'wb') as f:
#     pickle.dump(save_data, f)
# print("Clusters:", out[1])
# print("Changepoints:", out[2].flatten())
#
#
# #%% simu5: Oracle: changepoint_true / g_index_true init
# settings = ["inittruecp", "inittruecluster"]
# K_list = None
# for setting in settings:
#     print(setting)
#     if setting == "inittruecp":
#         g_index_init = None
#         changepoints_init = changepoints_true
#         init = "changepoints"
#     elif setting == "inittruecluster":
#         g_index_init = g_index_true
#         changepoints_init = None
#         init = "clustering"
#
#     out = mean_detect.fit(States_s, Actions, example=test_setting, C3=1.0, init=init,
#                           changepoints_init=changepoints_init, clustering_warm_start=0,
#                           g_index_init = g_index_init,
#                           K=K, threshold_type="permutation", B = 1000,
#                           seed=seed, nthread=num_threads, max_iter=15)
#     changepoint_err, cluster_err = evaluate(changepoints_true.squeeze(), out[1].squeeze(), out[2].squeeze(), N, T)
#     print('cp:', changepoint_err)
#     print('ari:', cluster_err)
#
#     iter_num = out[0] + 1
#     save_data = {
#         "model": out,
#         "changepoints": out[2],
#         "changepoint_err": changepoint_err,
#         "cluster_err": cluster_err,
#         "iter_num": iter_num}
#     file_name = path_name + "seed" + str(seed) + "_" + setting + "_cpresult" + ".dat"
#     with open(file_name, 'wb') as f:
#         pickle.dump(save_data, f)
#     print("Clusters:", out[1])
#     print("Changepoints:", out[2].flatten())
#
#
# # ### need to deal with label switching
# # # number of individuals each cluster
# # n_k = 25
# # from scipy.optimize import linear_sum_assignment
# # cluster_index = out[1].squeeze()
# # cluster_centers_true = []
# # cluster_centers_est = []
# # for k in range(K):
# #     cluster_centers_true.append(np.mean(States[0 + k * n_k:n_k + k * n_k, :, :], axis=0))
# #     cluster_centers_est.append(np.mean(States[cluster_index == k, :, :], axis=0))
# # # initialize cost matrix
# # cost_matrix = np.zeros(shape=(K, K))
# # # for each cluster
# # for k in range(K):
# #     for j in range(K):
# #         cost_matrix[k, j] = -cluster_centers_true[k].flatten() @ cluster_centers_est[j].flatten()
# #         # cost_matrix[k,j] = np.corrcoef(cluster_centers_true[k].flatten(), cluster_centers_est[k].flatten())[1,0]
# # row_ind, col_ind = linear_sum_assignment(cost_matrix)
# # cluster_index = np.argsort(col_ind)[cluster_index]
# #
# # changepoint_err, cluster_err = evaluate(changepoints_true.squeeze(), cluster_index, out[2].squeeze(), N, T)
# #
# # iter_num = out[0]
# # save_data = {
# #     'clusters': cluster_index,
# #     "changepoints": out[2],
# #     "changepoint_err": changepoint_err,
# #     "cluster_err": cluster_err,
# #     "iter_num": iter_num}
# # file_name = path_name + "seed" + str(seed) + "_cpresult" + ".dat"
# # # file_name = path_name + "cpresult_" + "seed" + str(seed) + ".dat"
# # with open(file_name, 'wb') as f:
# #     pickle.dump(save_data, f)
# #
# # print("Clusters:", out[1])
# # print("Changepoints:", out[2].flatten())

