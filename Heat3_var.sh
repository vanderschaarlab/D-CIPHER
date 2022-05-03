for noise_ratio in 0.0001 0.001 0.01 0.1
do
    echo "Noise ratio: $noise_ratio"
    python -m var_objective.run_var_square HeatEquation3_L1 0 2.0 30 $noise_ratio 200 HeatRandom 2spline2Dtrans 10 10 l1 lars-imp --seed 2 --num_samples 10;
done
