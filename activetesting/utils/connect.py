import json
import numpy as np
import openml
import os
import pandas as pd
import pickle
import math

def get_dataframe_from_openml(task_id, flow_id, num_runs, relevant_parameters, evaluation_measure, cache_directory):
    if 'y' in relevant_parameters:
        raise ValueError()

    try:
        os.makedirs(cache_directory + '/' + str(flow_id) + '/' + str(task_id))
    except FileExistsError:
        pass

    # grab num_runs random evaluations
    evaluations_cache_path = cache_directory + '/' + str(flow_id) + '/' + str(task_id) + '/evaluations.pkl'
    setups_cache_path = cache_directory + '/' + str(flow_id) + '/' + str(task_id) + '/setups.pkl'
    if not os.path.isfile(evaluations_cache_path) or not os.path.isfile(setups_cache_path):
        evaluations = {}
        for i in range(0, math.ceil(num_runs/500)):
            if i == math.ceil(num_runs/500) - 1:
                if num_runs%500 == 0:
                    evaluations.update(openml.evaluations.list_evaluations(evaluation_measure, size=500, task=[task_id], flow=[flow_id], offset=i*500))
                else:
                    evaluations.update(openml.evaluations.list_evaluations(evaluation_measure, size=num_runs%500, task=[task_id], flow=[flow_id], offset=i*500))
            else:
                evaluations.update(openml.evaluations.list_evaluations(evaluation_measure, size=500, task=[task_id], flow=[flow_id], offset=i*500))
        if len(evaluations) == 0:
            raise ValueError('No evaluations for this task. ')
        with open(evaluations_cache_path, 'wb') as fp:
            pickle.dump(evaluations, fp)
        print(len(evaluations))
        # setups
        setup_ids = []
        for run_id, evaluation in evaluations.items():
            setup_ids.append(evaluation.setup_id)
        
        setups = {}
        for i in range(0, math.ceil(len(setup_ids)/500)):
            if i == math.ceil(num_runs/500) - 1:
                setups.update(openml.setups.list_setups(setup=setup_ids[i*500:]))
            else:
                setups.update(openml.setups.list_setups(setup=setup_ids[i*500:i*500+500]))
        print(len(setups))
        with open(setups_cache_path, 'wb') as fp:
            pickle.dump(setups, fp)

    with open(evaluations_cache_path, 'rb') as fp:
        evaluations = pickle.load(fp)
    with open(setups_cache_path, 'rb') as fp:
        setups = pickle.load(fp)

    setup_parameters = {}

    for setup_id, setup in setups.items():
        hyperparameters = {}
        for pid, hyperparameter in setup.parameters.items():
            name = hyperparameter.parameter_name
            value = hyperparameter.value
            if name not in relevant_parameters.keys():
                continue

            if name in hyperparameters:
                # duplicate parameter name, this can happen due to subflows.
                # when this happens, we need to fix
                raise ValueError('Duplicate hyperparameter:', name, 'Values:', value, hyperparameters[name])
            hyperparameters[name] = value
        setup_parameters[setup_id] = hyperparameters
        if len(hyperparameters) != len(relevant_parameters):
            raise ValueError('Obtained parameters not complete. Setup id %d missing: %s' %(setup_id, str(relevant_parameters.keys() - hyperparameters.keys())))

    all_columns = list(relevant_parameters)
    all_columns.append('y')
    dataframe = pd.DataFrame(columns=all_columns)

    for run_id, evaluation in evaluations.items():
        currentXy = {}
        legalConfig = True
        for idx, param in enumerate(relevant_parameters):
            value = json.loads(setup_parameters[evaluation.setup_id][param])
            if relevant_parameters[param] == 'numeric':
                if not (isinstance(value, int) or isinstance(value, float)):
                    legalConfig = False

            currentXy[param] = value

        currentXy['y'] = evaluation.value

        if legalConfig:
            dataframe = dataframe.append(currentXy, ignore_index=True)
        else:
            # sometimes, a numeric param can contain string values. keep these out?
            print('skipping', currentXy)

    all_numeric_columns = list(['y'])
    for parameter, datatype in relevant_parameters.items():
        if datatype == 'numeric':
            all_numeric_columns.append(parameter)

    dataframe[all_numeric_columns] = dataframe[all_numeric_columns].apply(pd.to_numeric)

    if dataframe.shape[0] > num_runs:
        raise ValueError()
    if dataframe.shape[1] != len(relevant_parameters) + 1: # plus 1 for y data
        raise ValueError()

    dataframe = dataframe.reindex(sorted(dataframe.columns), axis=1)

    return dataframe


def get_X_y_from_openml(task_id, flow_id, num_runs, relevant_parameters, cache_directory):

    dataframe = get_dataframe_from_openml(task_id, flow_id, num_runs, relevant_parameters, cache_directory)

    categorical_columns = set(dataframe.columns) - set(dataframe._get_numeric_data().columns)
    categorical_indices = {dataframe.columns.get_loc(col_name) for col_name in categorical_columns}

    y = np.array(dataframe['y'], dtype=np.float)

    dataframe.drop('y', 1, inplace=True)
    return dataframe.as_matrix(), y, dataframe.columns.values, categorical_indices
