from __future__ import division, print_function, absolute_import

import argparse

# import seaborn
import sklearn
import sklearn.linear_model
import sklearn.ensemble
from sklearn.metrics import roc_curve
import numpy as np
import pylab as plt

from helpers import roc_auc, class_prob, cv_indices_generator
import data
import cv
from models import hyperparameter_grid

parser = argparse.ArgumentParser()
parser.add_argument("--plot-file",
    default="plot.png")

parser.add_argument("--bootstrap-iters",
    default=35,
    type=int,
    help="Number of bootstrap iterations (controls # of lines on ROC curve)")

parser.add_argument("--opacity",
    default=0.15,
    type=float,
    help="Alpha channel of plot")

parser.add_argument("--obliteration-years",
    default=4,
    type=int,
    help="Number of years to wait for obliteration")

parser.add_argument("--line-width",
    default=5,
    type=int,
    help="Line width for ROC curve plot")

parser.add_argument("--disable-feature-normalization",
    default=False,
    action="store_true",
    help="Don't subtract mean or divide by standard deviation")

parser.add_argument("--dpi", default=300, type=int)

def generate_roc_plot(
        X,
        Y,
        columns,
        classifier_class,
        classifier_hyperparameters,
        SM,
        VRAS,
        FP,
        obliteration_years=5,
        normalize_features=True,
        target_value=1,
        n_random_splits=50,
        line_width=5,
        alpha=0.18,
        dpi=300,
        filename="plot.png"):
    models = []
    auc_scores = []

    axes = plt.axes()

    for i, (train_indices, test_indices) in cv_indices_generator(len(X), n_random_splits):
        X_train = X[train_indices]
        X_test = X[test_indices]
        Y_train = Y[train_indices]
        Y_test = Y[test_indices]

        # skip any degenerate iterations
        if len(test_indices) == 0 or (Y_train == Y_train[0]).all() or (
                Y_test == Y_test[0]).all():
            print("Skipping iteration...")
            continue

        # use cross-validation over the bootstrap training set
        # to choose hyperparameters
        overall_best_results, results_per_class = cv.find_best_model(
            X_train,
            Y_train,
            {classifier_class: classifier_hyperparameters},
            target_value=1,
            normalize_features=normalize_features)
        best_model = overall_best_results.model
        params = overall_best_results.params

        # fit the best hyperparameter model with the full bootstrap training
        # set
        best_model.fit(X_train, Y_train)

        # print linear model coefficients for each feature
        for (col_name, coef) in zip(columns, list(best_model.coef_[0])):
            print("\t%s %s: %f" % ("-->" if coef != 0 else "   ", col_name, coef))

        print(">>> Fold Params", params)
        auc = roc_auc(best_model, X_test, Y_test)
        print(">>> Fold AUC", auc)
        models.append(best_model)
        auc_scores.append(auc)

        probs = class_prob(best_model, X_test)
        fpr, tpr, _ = roc_curve(Y_test, probs)
        axes.plot(
            fpr,
            tpr,
            lw=line_width,
            alpha=alpha if i > 0 else min(1.0, 2 * alpha),
            color=(0.15, 0.25, 0.7),
            label="LR" if i == 0 else "_")

        # need to make VRAS negative for ROC curve since it's
        # anti-correlated with good outcomes
        VRAS_fpr, VRAS_tpr, _ = roc_curve(Y_test, -VRAS[test_indices])
        axes.plot(
            VRAS_fpr,
            VRAS_tpr,
            lw=line_width,
            alpha=alpha if i > 0 else min(1.0, 2 * alpha),
            color=(0.7, 0.25, 0.1),
            label="VRAS" if i == 0 else "_")

        # need to make FP negative for ROC curve since it's
        # anti-correlated with good outcomes
        FP_fpr, FP_tpr, _ = roc_curve(Y_test, -FP[test_indices])
        axes.plot(
            FP_fpr,
            FP_tpr,
            lw=line_width,
            alpha=alpha if i > 0 else min(1.0, 2 * alpha),
            color=(0.1, 0.75, 0.2),
            markersize=2.0,
            label="FP" if i == 0 else "_")

        # need to make SM negative for ROC curve since it's
        # anti-correlated with good outcomes
        SM_fpr, SM_tpr, _ = roc_curve(Y_test, -SM[test_indices])
        axes.plot(
            SM_fpr,
            SM_tpr,
            alpha=alpha if i > 0 else min(1.0, 2 * alpha),
            lw=line_width,
            color=(0.7, 0.1, 0.4),
            markersize=2.0,
            label="SM" if i == 0 else "_")

    # diagonal line

    axes.plot([0, 1], [0, 1], '--', color=(0.6, 0.6, 0.6))

    axes.legend(loc="lower right")
    axes.set_aspect('equal')
    axes.set_xlim(0, 1)
    axes.set_ylim(0, 1)

    # axes.legend()
    plt.xlabel('False Positive Rate')
    plt.ylabel('True Positive Rate')
    plt.title('Time Horizon = %d Years' % obliteration_years)
    figure = axes.figure
    figure.savefig(filename, dpi=dpi)
    print("\n >>> Average AUC score across all bootstrap samples: %0.4f" % (
        np.mean(auc_scores),))
    return models


if __name__ == "__main__":
    args = parser.parse_args()
    dataset, full_df = data.load_datasets(
        obliteration_years=args.obliteration_years)
    X = dataset["X"]
    Y = dataset["Y"]
    assert len(X) == len(Y)
    columns = dataset["df_filtered"].columns
    VRAS = dataset["VRAS"]
    FP = dataset["FP"]
    SM = dataset["SM"]

    Y_binary = Y == 2
    lr_hyperparameters = list(
        hyperparameter_grid(logistic_regression=True).values())[0]
    print(lr_hyperparameters)
    all_models = generate_roc_plot(
        X,
        Y_binary,
        columns,
        classifier_class=sklearn.linear_model.LogisticRegression,
        classifier_hyperparameters=lr_hyperparameters,
        SM=SM,
        VRAS=VRAS,
        FP=FP,
        target_value=1,
        obliteration_years=args.obliteration_years,
        normalize_features=not args.disable_feature_normalization,
        n_random_splits=args.bootstrap_iters,
        alpha=args.opacity,
        dpi=args.dpi,
        line_width=args.line_width,
        filename=args.plot_file)
    feature_nonzero_counts = np.zeros(len(columns), dtype=int)
    for model in all_models:
        feature_nonzero_counts[model.coef_[0] != 0] += 1
    feature_nonzero_fractions = feature_nonzero_counts / float(len(all_models))

    print("Feature Utilization by CV models")
    for i in np.argsort(feature_nonzero_fractions):
        feature = columns[i]
        fraction = feature_nonzero_fractions[i]
        print("\t %30s: %0.4f" % (feature, fraction))
