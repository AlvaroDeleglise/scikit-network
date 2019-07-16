#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Mar 3, 2019
@author: Nathan de Lara <ndelara@enst.fr>
@author: Thomas Bonald <bonald@enst.fr>
"""

import numpy as np
from scipy import sparse
from typing import Union, Optional
from sknetwork.clustering.louvain import Louvain, GreedyModularity, Optimizer
from sknetwork.clustering.postprocessing import reindex_clusters
from sknetwork.utils.adjacency_formats import bipartite2undirected, bipartite2directed
from sknetwork.utils.checks import check_probs, check_format, check_engine, check_random_state
from sknetwork.utils.algorithm_base_class import Algorithm


class BiLouvain(Algorithm):
    """
    BiLouvain algorithm for the co-clustering of bipartite graphs.

    Seeks the best partition of the nodes with respect to bimodularity.

    The bimodularity of a clustering is

    :math:`Q = \\sum_{i=1}^n\\sum_{j=1}^p\\big(\\dfrac{B_{ij}}{w} -
    \\gamma \\dfrac{d_if_j}{w^2}\\big)\\delta_{c^d_i,c^f_j}`,

    where

    :math:`d_i` is the weight of sample node :math:`i` (rows of the biadjacency matrix),\n
    :math:`f_j` is the weight of feature node :math:`j` (columns of the biadjacency matrix),\n
    :math:`c^d_i` is the cluster of sample node :math:`i`,\n
    :math:`c^f_j` is the cluster of feature node :math:`j`,\n
    :math:`\\delta` is the Kronecker symbol,\n
    :math:`\\gamma \\ge 0` is the resolution parameter.

    The `force_undirected` parameter of the :class:`fit` method forces the algorithm to consider the graph
    as undirected, without considering its bipartite structure.

    Parameters
    ----------
    algorithm :
        The optimization algorithm.
        Requires a fit method.
        Requires `score\\_`  and `labels\\_` attributes.

        If ``'default'``, uses greedy modularity optimization algorithm: :class:`GreedyModularity`.
    engine : str
        ``'default'``, ``'python'`` or ``'numba'``. If ``'default'``, tests if numba is available.
    resolution :
        Resolution parameter.
    tol :
        Minimum increase in the objective function to enter a new optimization pass.
    agg_tol :
        Minimum increase in the objective function to enter a new aggregation pass.
    max_agg_iter :
        Maximum number of aggregations.
        A negative value is interpreted as no limit.
    verbose :
        Verbose mode.

    Attributes
    ----------
    labels_ : np.ndarray
        Labels of sample nodes (rows).
    feature_labels_ : np.ndarray
        Labels of feature nodes (columns).
    iteration_count_ : int
        Total number of aggregations performed.
    aggregate_graph_ : sparse.csr_matrix
        Aggregated adjacency at the end of the algorithm.
    score_ : float
        objective function value after fit
    n_clusters_ : int
        number of clusters after fit
    """

    def __init__(self, engine: str = 'default', algorithm: Union[str, Optimizer] = 'default', resolution: float = 1,
                 tol: float = 1e-3, agg_tol: float = 1e-3, max_agg_iter: int = -1,
                 random_state: Optional[Union[np.random.RandomState, int]] = None, verbose: bool = False):
        self.random_state = check_random_state(random_state)
        if algorithm == 'default':
            self.algorithm = GreedyModularity(resolution, tol, engine=check_engine(engine))
        elif isinstance(algorithm, Optimizer):
            self.algorithm = algorithm
        else:
            raise TypeError('Algorithm must be \'auto\' or a valid algorithm.')
        self.resolution = resolution
        self.tol = tol
        self.agg_tol = agg_tol
        if type(max_agg_iter) != int:
            raise TypeError('The maximum number of iterations must be an integer.')
        self.max_agg_iter = max_agg_iter
        self.engine = check_engine(engine)
        self.verbose = verbose
        self.labels_ = None
        self.feature_labels_ = None
        self.iteration_count_ = None
        self.aggregate_graph_ = None
        self.score_ = None
        self.n_clusters_ = None

    def fit(self, biadjacency: sparse.csr_matrix, weights: Union['str', np.ndarray] = 'degree',
            feature_weights: Union['str', np.ndarray] = 'degree', force_undirected: bool = False,
            sorted_cluster: bool = True):
        """
        Alternates local optimization and aggregation until convergence.

        Parameters
        ----------
        biadjacency :
            Biadjacency matrix of the graph.
        weights :
            Probabilities for the samples in the null model. ``'degree'``, ``'uniform'`` or custom weights.
        feature_weights :
            Probabilities for the features in the null model. ``'degree'``, ``'uniform'`` or custom weights.
        force_undirected :
            If True, maximizes the modularity of the undirected graph instead of the bimodularity.
        sorted_cluster :
            If True, sort labels in decreasing order of cluster size.
        """
        biadjacency = check_format(biadjacency)
        n, p = biadjacency.shape

        louvain = Louvain(algorithm=self.algorithm, verbose=self.verbose)

        if force_undirected:
            adjacency = bipartite2undirected(biadjacency)
            samp_weights = check_probs(weights, biadjacency)
            feat_weights = check_probs(feature_weights, biadjacency.T)
            weights = np.hstack((samp_weights, feat_weights))
            weights = check_probs(weights, adjacency)
            louvain.fit(adjacency, weights)
        else:
            adjacency = bipartite2directed(biadjacency)
            samp_weights = np.hstack((check_probs(weights, biadjacency), np.zeros(p)))
            feat_weights = np.hstack((np.zeros(n), check_probs(feature_weights, biadjacency.T)))
            louvain.fit(adjacency, samp_weights, feat_weights)

        self.n_clusters_ = louvain.n_clusters_
        self.iteration_count_ = louvain.iteration_count_
        labels = louvain.labels_
        if sorted_cluster:
            labels = reindex_clusters(labels)
        self.labels_ = labels[:n]
        self.feature_labels_ = labels[n:]
        self.aggregate_graph_ = louvain.aggregate_graph_ * adjacency.data.sum()
