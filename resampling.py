#!/usr/local/bin/python3

import json
import mne
import warnings
import numpy as np
import os
import shutil
import pandas as pd
from mne_bids import BIDSPath, write_raw_bids
from collections import Counter
from brainlife_apps_helper import helper


def resampling(data, events_matrix, param_epoched_data, param_sfreq, param_npad, param_window,
               param_stim_picks, param_n_jobs, param_raw_pad, param_epoch_pad, 
               param_save_jointly_resampled_events):
    """Resample the signals using MNE Python and save the file once resampled.

    Parameters
    ----------
    data: instance of mne.io.Raw or instance of mne.Epochs
        Data to be resampled.
    events_matrix: np.array or None
        The event matrix (2D array, shape (n_events, 3)). 
        When specified, the onsets of the events are resampled jointly with the data
    param_epoched_data: bool
        If True, the data to be resampled is epoched, else it is continuous.
    param_sfreq: float
        New sample rate to use in Hz.
    param_npad: int or str
        Amount to pad the start and end of the data. Can be “auto” (default).
    param_window: str
        Frequency-domain window to use in resampling. Default is "boxcar". 
    param_stim_picks: list of int or None
        Stim channels.
    param_n_jobs: int or str
        Number of jobs to run in parallel. Can be ‘cuda’ if cupy is installed properly. Default is 1.
    param_raw_pad: str
        The type of padding to use for raw data. Supports all numpy.pad() mode options. Can also be 
        “reflect_limited” (default) and "edge".
    param_epoch_pad: str
        The type of padding to use for epoched data. Supports all numpy.pad() mode options. Can also be 
        “reflect_limited” and "edge" (default).
    param_save_jointly_resampled_events: bool
        If True, save the events file resampled jointly with the data.

    Returns
    -------
    data_resampled: instance of mne.io.Raw or instance of mne.Epochs
        The data after resampling.
    events: array, shape (n_events, 3) or None
        If events are jointly resampled, these are returned with the raw.
        The input events are not modified.
    """

    # For continuous data 
    if param_epoched_data is False:

        # Load data
        data.load_data()

        # Test if events file exist
        if events_matrix is not None and param_save_jointly_resampled_events is True:

            # Resample data
            data_resampled, events_resampled = data.resample(sfreq=param_sfreq, npad=param_npad, window=param_window,
                                                             stim_picks=param_stim_picks, n_jobs=param_n_jobs,
                                                             events=events_matrix, pad=param_raw_pad)
        else:
            # Resample data
            data_resampled = data.resample(sfreq=param_sfreq, npad=param_npad, window=param_window,
                                           stim_picks=param_stim_picks, n_jobs=param_n_jobs,
                                           events=None, pad=param_raw_pad)
            events_resampled = None

    # For epoched data 
    else:

        # Resample data
        data_resampled = data.resample(sfreq=param_sfreq, npad=param_npad, 
                                       window=param_window, n_jobs=param_n_jobs, 
                                       pad=param_epoch_pad)
        events_resampled = None

    # Save file
    data_resampled.save("out_dir_resampling/meg.fif", overwrite=True)

    return data_resampled, events_resampled


def main():

    # Generate a json.product to display messages on Brainlife UI
    dict_json_product = {'brainlife': []}

    # Load inputs from config.json
    with open('config.json') as config_json:
        config = json.load(config_json)

    # Read the files
    data_file = config.pop('fif')
    if config['param_epoched_data'] is False:
        data = mne.io.read_raw_fif(data_file, allow_maxshield=True)
    else:
        data = mne.read_epochs(data_file)

    # Read and save optional files
    config, cross_talk_file, calibration_file, events_file, head_pos_file, channels_file, destination = helper.read_optional_files(config, 'out_dir_resampling')
    
    # Convert empty strings values to None
    config = helper.convert_parameters_to_None(config)

    # Channels.tsv must be BIDS compliant
    if channels_file is not None:
        user_warning_message_channels = f'The channels file provided must be ' \
                                        f'BIDS compliant and the column "status" must be present. ' 
        warnings.warn(user_warning_message_channels)
        dict_json_product['brainlife'].append({'type': 'warning', 'msg': user_warning_message_channels})
        # Udpate data.info['bads'] with info contained in channels.tsv
        data, user_warning_message_channels = helper.update_data_info_bads(data, channels_file)
        if user_warning_message_channels is not None: 
            warnings.warn(user_warning_message_channels)
            dict_json_product['brainlife'].append({'type': 'warning', 'msg': user_warning_message_channels})


    # Extract the matrix of events # 
    if config['param_epoched_data'] is False:
        if events_file is not None:
            # Warning: events file must be BIDS compliant  
            user_warning_message_events = f'The events file provided must be ' \
                                          f'BIDS compliant.'        
            warnings.warn(user_warning_message_events)
            dict_json_product['brainlife'].append({'type': 'warning', 'msg': user_warning_message_events})
            ############### TO BE TESTED ON NO RESTING STATE DATA
            # Compute the events matrix #
            df_events = pd.read_csv(events_file, sep='\t')
            
            # Extract relevant info from df_events
            samples = df_events['sample'].values
            event_id = df_events['value'].values

            # Compute the values for events matrix 
            events_time_in_sample = [data.first_samp + sample for sample in samples]
            values_of_trigger_channels = [0]*len(events_time_in_sample)

            # Create a dataframe
            df_events_matrix = pd.DataFrame([events_time_in_sample, values_of_trigger_channels, event_id])
            df_events_matrix = df_events_matrix.transpose()

            # Convert dataframe to numpy array
            events_matrix = df_events_matrix.to_numpy()
        else:
            events_matrix = None  
    else:
        events_matrix = None               
        
    
    # Info message about resampling if applied
    if config['param_epoched_data'] is False:
        dict_json_product['brainlife'].append({'type': 'info', 'msg': f'Data was resampled at '
                                                                      f'{config["param_sfreq"]}. '
                                                                      f'Please bear in mind that it is generally '
                                                                      f'recommended not to epoch '
                                                                      f'downsampled data, but instead epoch '
                                                                      f'and then downsample.'})
    
    # Comment about resampling
    comments_resample_freq = f'{config["param_sfreq"]}Hz'

    # Check if the user will save an empty events file 
    if events_file is None and config['param_save_jointly_resampled_events'] is True:
        value_error_message = f'You cannot save en empty events file. ' \
                              f"If you haven't an events file, please set " \
                              f"'param_save_jointly_resampled_event' to False."
        # Raise exception
        raise ValueError(value_error_message)

    
    ## Convert parameters ##

    # Deal with param_npad parameter #
    # Convert param_npad into int if not "auto" when the App is run on BL
    if config['param_npad'] != "auto":
        config['param_npad'] = int(config['param_npad'])

    # Deal with param_n_jobs parameter #
    # Convert n jobs into int when the App is run on BL
    if config['param_n_jobs'] != 'cuda':
        config['param_n_jobs']  = int(config['param_n_jobs'])

    # Deal with stim picks parameter #
    # Convert stim picks into a list of int when the App is run on BL
    if isinstance(config['param_stim_picks'], str) and config['param_stim_picks'] is not None:
        config['param_stim_picks'] = config['param_stim_picks'].replace('[', '')
        config['param_stim_picks'] = config['param_stim_picks'].replace(']', '')
        config['param_stim_picks'] = list(map(int, config['param_stim_picks'].split(', ')))

    # Keep bad channels in memory
    bad_channels = data.info['bads']


    # Define the type of data
    data = data.pick(picks=config['param_pick_type'])

    # Delete keys values in config.json when this app is executed on Brainlife
    del config['param_pick_type']
    kwargs = helper.define_kwargs(config)

    # Apply resampling
    data_copy = data.copy()
    data_resampled, events_resampled = resampling(data_copy, events_matrix, **kwargs)
    del data_copy

    ## Create BIDS compliant events file if existed ## 
    if events_resampled is not None and config['param_epoched_data'] is False:
        # Create a BIDSPath
        bids_path = BIDSPath(subject='subject',
                             session=None,
                             task='task',
                             run='01',
                             acquisition=None,
                             processing=None,
                             recording=None,
                             space=None,
                             suffix=None,
                             datatype='meg',
                             root='bids')

        # Extract event_id value #
        # to be tested when events are extracted from data
        event_id_value = list(events_resampled[:, 2])  # the third column of events corresponds to the value column of BIDS events.tsv
        id_values_occurrences = Counter(event_id_value)  # number of different events
        id_values_occurrences = list(id_values_occurrences.keys())
        trials_type = [f"events_{i}" for i in range(1, len(id_values_occurrences) + 1)]  # for trial type column of BIDS events.tsv 
        dict_event_id = dict((k, v) for k, v  in zip(trials_type, id_values_occurrences))


        # Write BIDS to create events.tsv BIDS compliant
        write_raw_bids(data, bids_path, events_data=events_resampled, event_id=dict_event_id, overwrite=True)

        # Extract events.tsv from bids path
        events_file = 'bids/sub-subject/meg/sub-subject_task-task_run-01_events.tsv'

        # Copy events.tsv in outdir
        shutil.copy2(events_file, 'out_dir_resampling/events.tsv') 

        # Info message in product.json
        dict_json_product['brainlife'].append({'type': 'info', 'msg': 'Jointly resampled events are saved in events.tsv.'})


    # Success message in product.json    
    dict_json_product['brainlife'].append({'type': 'success', 'msg': 'Data was successfully resampled.'})


    # Save the dict_json_product in a json file
    with open('product.json', 'w') as outfile:
        json.dump(dict_json_product, outfile)


if __name__ == '__main__':
    main()
