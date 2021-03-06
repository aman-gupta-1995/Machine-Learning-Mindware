import time
from typing import List
from collections import OrderedDict

from openbox.utils.constants import MAXINT
from openbox.core.sync_batch_advisor import SyncBatchAdvisor
from openbox.core.async_batch_advisor import AsyncBatchAdvisor
from openbox.optimizer.base import BOBase
from openbox.core.message_queue.master_messager import MasterMessager
from openbox.core.base import Observation


class mqSMBO(BOBase):
    def __init__(self, objective_function, config_space,
                 eval_type='holdout',
                 parallel_strategy='async',
                 batch_size=4,
                 batch_strategy='median_imputation',
                 num_constraints=0,
                 num_objs=1,
                 sample_strategy: str = 'bo',
                 runtime_limit=600,
                 time_limit_per_trial=180,
                 surrogate_type=None,
                 acq_type=None,
                 acq_optimizer_type='local_random',
                 initial_runs=3,
                 init_strategy='random_explore_first',
                 initial_configurations=None,
                 ref_point=None,
                 history_bo_data: List[OrderedDict] = None,
                 logging_dir='logs',
                 task_id='default',
                 random_state=1,
                 ip="",
                 port=13579,
                 authkey=b'abc', ):

        self.task_info = {'num_constraints': num_constraints, 'num_objs': num_objs}
        self.FAILED_PERF = [MAXINT] * num_objs
        super().__init__(objective_function, config_space, task_id=task_id, output_dir=logging_dir,
                         random_state=random_state, initial_runs=initial_runs, max_runs=int(1e10),
                         runtime_limit=runtime_limit, sample_strategy=sample_strategy,
                         time_limit_per_trial=time_limit_per_trial, history_bo_data=history_bo_data)
        if parallel_strategy == 'sync':
            self.config_advisor = SyncBatchAdvisor(config_space, self.task_info,
                                                   batch_size=batch_size,
                                                   batch_strategy=batch_strategy,
                                                   initial_trials=initial_runs,
                                                   initial_configurations=initial_configurations,
                                                   init_strategy=init_strategy,
                                                   history_bo_data=history_bo_data,
                                                   optimization_strategy=sample_strategy,
                                                   surrogate_type=surrogate_type,
                                                   acq_type=acq_type,
                                                   acq_optimizer_type=acq_optimizer_type,
                                                   ref_point=ref_point,
                                                   task_id=task_id,
                                                   output_dir=logging_dir,
                                                   random_state=random_state)
        elif parallel_strategy == 'async':
            self.config_advisor = AsyncBatchAdvisor(config_space, self.task_info,
                                                    batch_size=batch_size,
                                                    batch_strategy=batch_strategy,
                                                    initial_trials=initial_runs,
                                                    initial_configurations=initial_configurations,
                                                    init_strategy=init_strategy,
                                                    history_bo_data=history_bo_data,
                                                    optimization_strategy=sample_strategy,
                                                    surrogate_type=surrogate_type,
                                                    acq_type=acq_type,
                                                    acq_optimizer_type=acq_optimizer_type,
                                                    ref_point=ref_point,
                                                    task_id=task_id,
                                                    output_dir=logging_dir,
                                                    random_state=random_state)
        else:
            raise ValueError('Invalid parallel strategy - %s.' % parallel_strategy)

        self.eval_type = eval_type
        self.parallel_strategy = parallel_strategy
        self.batch_size = batch_size
        max_queue_len = max(100, 3 * batch_size)
        self.master_messager = MasterMessager(ip, port, authkey, max_queue_len, max_queue_len)
        self.start_time = time.time()

        self.configs = list()
        self.perfs = list()
        self.incumbent_perf = float("-INF")
        self.incumbent_config = self.config_space.get_default_configuration()
        self.eval_dict = dict()
        self.workers = dict()

    def async_run(self):
        config_num = 0
        cur_num = 0
        while time.time() - self.start_time < self.runtime_limit:
            # Add jobs to masterQueue.
            while len(self.config_advisor.running_configs) < self.batch_size and config_num < self.max_iterations:
                config_num += 1
                config = self.config_advisor.get_suggestion()
                msg = [config, self.time_limit_per_trial]
                self.logger.info("Master: Add config %d." % config_num)
                self.master_messager.send_message(msg)

            # Get results from workerQueue.
            while True:
                observation = self.master_messager.receive_message()
                if observation is None:
                    # Wait for workers.
                    # self.logger.info("Master: wait for worker results. sleep 1s.")
                    time.sleep(1)
                    break
                # Report result.
                cur_num += 1
                config, trial_state, constraints, objs, elapsed_time, worker_info, extra_info = observation

                stored_info = list(self.workers.values())
                if worker_info not in stored_info:
                    self.workers[len(self.workers)] = worker_info

                _perf = float("INF") if objs is None else objs[0]
                self.configs.append(config)
                self.perfs.append(_perf)
                self.eval_dict[config] = [-_perf, time.time(), trial_state]

                if -_perf > self.incumbent_perf:
                    self.incumbent_perf = -_perf
                    self.incumbent_config = config

                if objs is None:
                    observation = Observation(config, trial_state, constraints, self.FAILED_PERF, elapsed_time,
                                              worker_info=worker_info, extra=extra_info)
                self.config_advisor.update_observation(observation)

                self.logger.info('Master: Get %d observation: %s' % (cur_num, str(observation)))

    def sync_run(self):
        batch_id = 0
        while time.time() - self.start_time < self.runtime_limit:
            configs = self.config_advisor.get_suggestions()
            # Add batch configs to masterQueue.
            for config in configs:
                msg = [config, self.time_limit_per_trial]
                self.master_messager.send_message(msg)
            self.logger.info('Master: %d-th batch. %d configs sent.' % (batch_id, len(configs)))
            # Get batch results from workerQueue.
            result_num = 0
            result_needed = len(configs)
            while True:
                observation = self.master_messager.receive_message()
                if observation is None:
                    # Wait for workers.
                    # self.logger.info("Master: wait for worker results. sleep 1s.")
                    time.sleep(1)
                    continue
                # Report result.
                result_num += 1
                config, trial_state, constraints, objs, elapsed_time, worker_info, extra_info = observation
                if objs is None:
                    observation = Observation(config, trial_state, constraints, self.FAILED_PERF, elapsed_time,
                                              worker_info, extra_info)
                self.config_advisor.update_observation(observation)
                self.logger.info('Master: In the %d-th batch [%d], observation is: %s'
                                 % (batch_id, result_num, str(observation)))
                if result_num == result_needed:
                    break
            batch_id += 1

    def run(self):
        if self.parallel_strategy == 'async':
            self.async_run()
        else:
            self.sync_run()

        return self.get_history()
