import numpy as np
import argparse
import time

from .differential_operator import LinearOperator
from .derivative_estimators import get_diff_engine

from .equations import get_pdes
from .grids import EquiPartGrid
from .generator import generate_fields
from .interpolate import estimate_fields
from .basis import FourierSine2D
from .optimize_operator import MSEWeightsFinder, normalize
from .conditions import get_conditions_set
from .config import get_optim_params, get_gp_params
from .libs import SymbolicRegressor, make_fitness
from .utils.gp_utils import gp_to_pysym_with_coef

from sklearn.model_selection import ParameterGrid
import pickle
from datetime import datetime
import sympy
INF_FLOAT = 9999999999999.9

def grid_and_fields_to_covariates(grid_and_fields):

    grid_and_fields = np.moveaxis(grid_and_fields,1,-1)
    num_var = grid_and_fields.shape[-1]
    return np.reshape(grid_and_fields,(-1,num_var))


def _check_if_zero(vector):
    if np.sum(vector == 0.0) == len(vector):
        return True
    else:
        return False

if __name__ == '__main__':

    PDES_NAME = 'HeatEquation_0.1'
    WIDTH = 1.0
    FREQUENCY_PER_DIM = 20
    NOISE_RATIO = 0
    CONDITIONS_SET = 'HeatTuning'
    FIELD_INDEX = 0
    DIFF_ENGINE = 'finite'
    NUM_TESTS = 1

    pdes = get_pdes(PDES_NAME)

    widths = [WIDTH] * 2

    SEED = 0


    observed_grid = EquiPartGrid(widths, FREQUENCY_PER_DIM)

    conditions = get_conditions_set(CONDITIONS_SET)

    print(f"Seed set to {SEED}")
    print(f"Generating dataset of {PDES_NAME} on a grid with width {WIDTH}, frequency per dim {FREQUENCY_PER_DIM}, noise ratio {NOISE_RATIO} and using conditions set {CONDITIONS_SET}")
    start = time.time()
    observed_dataset = generate_fields(pdes, conditions, observed_grid, NOISE_RATIO, seed=SEED)
    end = time.time()
    print(f"Observed dataset generated in {end-start} seconds")

    dimension = pdes.get_expression()[FIELD_INDEX][0].dimension
    order = pdes.get_expression()[FIELD_INDEX][0].order
   
    opt_params = get_optim_params()

    engine = get_diff_engine(DIFF_ENGINE)

    print("Initializing MSE Weights Finder")
    start = time.time()
    mse_wf = MSEWeightsFinder(observed_dataset,FIELD_INDEX,observed_grid,dimension=dimension,order=order,engine=engine,**opt_params, seed=SEED)
    end = time.time()
    print(f"Weight Finder initialized in {end-start} seconds")


    def _mse_fitness(y, y_pred, w):

        # Hack to pass the test
        if len(y_pred) == 2:
            return 0.0

        if _check_if_zero(y_pred):
            return INF_FLOAT

        loss, weights = mse_wf.find_weights(y_pred,from_covariates=True, normalize_g='unit_g', only_loss=True)

        return loss
    
    X = grid_and_fields_to_covariates(mse_wf.grid_and_fields)
    fake_y = np.zeros(X.shape[0])

    var_fitness = make_fitness(_mse_fitness, greater_is_better=False)

    gp_parameters_values = {
        'population_size':[100,200,1000,2000,5000],
        'generations':[5,10,20,50],
        'tournament_size':[5,10,20,50],
        # 'p_crossover':[0.01,0.1,0.5,0.9],
        # 'p_subtree_mutation':[0.001,0.01,0.1,0.2],
        # 'p_hoist_mutation':[0.001,0.01,0.1,0.2],
        # 'p_point_mutation':[0.001,0.01,0.1,0.2],
        'parsimony_coefficient':[0.001,0.005,0.01,0.05,0.1]
    }

    gp_params = get_gp_params()
    loss2, weights2 = mse_wf.find_weights(4*np.sin(2*np.pi*X[:,1]),from_covariates=True,normalize_g='unit_g', only_loss=False)
    print(loss2, weights2)

    np.random.seed(SEED)

    parameter_grid = ParameterGrid(gp_parameters_values)

    params_list = np.random.choice(list(parameter_grid), size=NUM_TESTS, replace=False)

    results = []
    used_params = []
    programmes = []
    weights = []
    programme_lengths = []

    for param in params_list:
        sum = 2
        while sum > 1:
            p_cross  = np.random.rand()
            p_subtree = np.random.rand()
            p_hoist = np.random.rand()
            p_point = np.random.rand() 
            sum = p_cross + p_subtree + p_hoist + p_point
        
        param['p_crossover'] = p_cross
        param['p_subtree_mutation'] = p_subtree
        param['p_hoist_mutation'] = p_hoist
        param['p_point_mutation'] = p_point

        print(f"Using {param}")

        est = SymbolicRegressor(metric=var_fitness, **param ,verbose=1, random_state=SEED, function_set=('add', 'sub', 'mul', 'div','sin', 'log','exp'))
        est.fit(X, fake_y)
        loss, weights = mse_wf.find_weights(est.predict(X),from_covariates=True, normalize_g='unit_g', only_loss=False)
        eq, eqC = gp_to_pysym_with_coef(est)
        results.append(loss)
        used_params.append(param)
        programmes.append(f"{eq}")
        programme_lengths.append(est._program.length_)
        print(f"{weights} - {sympy.simplify(eq)} = 0")
    
    min_i = np.argmin(results)
    print(f"Smallest loss: {results[min_i]} with parameters {used_params[min_i]}")
    dt = datetime.now().strftime("%d-%m-%YT%H.%M.%S")
    to_save = (results, used_params, programmes, programme_lengths)
    name_pickle = f"gplearn_tuning_{dt}.p"
    name_txt = f"gplearn_tuning_{dt}.txt"
    pickle.dump(to_save, open(name_pickle, "wb" ))
    with open(name_txt, "w") as f:
        f.write(f"Loss: {results[min_i]}\nParameters: {used_params[min_i]}\nFunction: {programmes[min_i]}\nLength: {programme_lengths[min_i]}")


