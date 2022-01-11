import numpy as np
import argparse
import time

from var_objective.differential_operator import LinearOperator

from .equations import get_pdes
from .grids import EquiPartGrid
from .generator import generate_fields
from .interpolate import estimate_fields
from .basis import BSplineFreq2D, Fake, FourierSine2D
from .optimize_operator import VariationalWeightsFinder, normalize
from .conditions import get_conditions_set
from .config import get_optim_params, get_gp_params
from .libs import SymbolicRegressor, make_fitness

INF = 99999999.9


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

    parser = argparse.ArgumentParser(description="Discover a PDE")
    parser.add_argument('name', help='Equation name from equations.py')
    parser.add_argument('field_index', type=int, help='Which field coordinate to model')
    parser.add_argument('width', type=float, help='Width of the grid')
    parser.add_argument('frequency_per_dim', type=int, help='Frequency per dimension of generated data')
    parser.add_argument('noise_ratio', type=float, help='Noise ration for data generation')
    parser.add_argument('full_grid_samples', type=int, help='Frequency of the full grid')
    parser.add_argument('conditions_set', help='Conditions set name from conditions.py')
    parser.add_argument('basis', choices=['fourier','2spline2D','fake'])
    parser.add_argument('max_ind_basis', type=int, help='Maximum index for test functions. Number of used test functions is a square of this number')
    parser.add_argument('num_trials', type=int, help='Number of trials')
    parser.add_argument('--seed', type=int, default=0)

    args = parser.parse_args()

    INF_FLOAT = 9999999999999.9

    pdes = get_pdes(args.name)

    widths = [args.width] * 2


    observed_grid = EquiPartGrid(widths, args.frequency_per_dim)
    full_grid = EquiPartGrid(widths, args.full_grid_samples)

    conditions = get_conditions_set(args.conditions_set)

    print(f"Seed set to {args.seed}")
    print(f"Generating dataset of {args.name} on a grid with width {args.width}, frequency per dim {args.frequency_per_dim}, noise ratio {args.noise_ratio} and using conditions set {args.conditions_set}")
    start = time.time()
    observed_dataset = generate_fields(pdes, conditions, observed_grid, args.noise_ratio, seed=args.seed)
    end = time.time()
    print(f"Observed dataset generated in {end-start} seconds")

    print(f"Estimating fields on a grid with frequency {args.full_grid_samples} per dimension")
    start = time.time()
    full_dataset = estimate_fields(observed_grid,observed_dataset,full_grid,seed=args.seed)
    end = time.time()
    print(f"Fields estimated in {end-start} seconds")

    # a = full_dataset[0,0].shape[0]
    # b = full_dataset[0,0].shape[1]


    # from matplotlib import pyplot as plt
    # from matplotlib import animation

    # # First set up the figure, the axis, and the plot element we want to animate
    # fig = plt.figure()
    # ax = plt.axes(xlim=(0, 1.0), ylim=(-5.0,5.0))
    # line, = ax.plot([], [], lw=2)

    # # initialization function: plot the background of each frame
    # def init():
    #     line.set_data([], [])
    #     return line,

    # # animation function.  This is called sequentially
    # def animate(i):
        
    #     line.set_data(np.linspace(0.0,1.0,b), full_dataset[0,0][i,:])
    #     ax.set_title(f"Frame {i}")
    #     return line,

    # # call the animator.  blit=True means only re-draw the parts that have changed.
    # anim = animation.FuncAnimation(fig, animate, init_func=init,
    #                             frames=a, interval=10, blit=True)

    # plt.show()



    dimension = pdes.get_expression()[args.field_index][0].dimension
    order = pdes.get_expression()[args.field_index][0].order

    if args.basis == 'fourier':
        basis = FourierSine2D(widths)
        index_limits = [args.max_ind_basis] * 2
    elif args.basis == '2spline2D':
        basis = BSplineFreq2D(widths, 2)
        index_limits = [args.max_ind_basis] * 2
    elif args.basis == 'fake':
        basis = Fake(widths)
        index_limits = [args.max_ind_basis] * 2
   
    opt_params = get_optim_params()

    print("Initializing Variational Weights Finder")
    start = time.time()
    var_wf = VariationalWeightsFinder(full_dataset,args.field_index,full_grid,dimension=dimension,order=order,basis=basis,index_limits=index_limits,**opt_params, seed=args.seed)
    end = time.time()
    print(f"Weight Finder initialized in {end-start} seconds")


    def _var_fitness(y, y_pred, w):

        if len(y_pred) == 2:
            print("Test")
            return 0.0

        if _check_if_zero(y_pred):
            return INF

        loss, weights = var_wf.find_weights(y_pred,from_covariates=True, normalize_g=True)

        return loss
    
    X = grid_and_fields_to_covariates(var_wf.grid_and_fields)
    fake_y = np.zeros(X.shape[0])

    var_fitness = make_fitness(_var_fitness, greater_is_better=False)

    gp_params = get_gp_params()


    loss2, weights2 = var_wf.find_weights(4*np.sin(2*np.pi*X[:,1]),from_covariates=True,normalize_g=False)

    print(loss2, weights2)

    loss3, weights3 = var_wf.find_weights(np.sin(X[:,2]-X[:,1]),from_covariates=True,normalize_g=False)

    print(loss3, weights3)



    est = SymbolicRegressor(metric=var_fitness, **gp_params ,verbose=1, random_state=args.seed)

    est.fit(X, fake_y)



    loss, weights = var_wf.find_weights(est.predict(X),from_covariates=True,normalize_g=False)

    linear_operator = LinearOperator.from_vector(weights, dimension, order, zero_partial=False)
    print(f"{linear_operator.get_adjoint()} - {est._program} = 0")





# mse_wf = MSEWeightsFinder(observed_dataset,0,observed_grid,2,1,NumpyDiff(),alpha=1.0,beta=0.2,optim_name='sgd',optim_params={'lr':0.01},num_epochs=300,patience=20)
 

#TODO: incorporate w somehow
# def _mse_fitness(y, y_pred, w):
#     if len(y_pred) == 2:
#         print("Test")
#         return 0.0

#     loss, weights = mse_wf.find_weights(y_pred,from_covariates=True)

#     return loss


# mse_fitness = make_fitness(_mse_fitness, greater_is_better=False)
