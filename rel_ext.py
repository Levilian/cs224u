from collections import Counter, defaultdict, namedtuple
import gzip
import numpy as np
import os
import random
from sklearn.feature_extraction import DictVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import precision_recall_fscore_support
from sklearn.model_selection import train_test_split

__author__ = "Bill MacCartney"
__version__ = "CS224u, Stanford, Spring 2019"


Example = namedtuple('Example',
    'entity_1, entity_2, left, mention_1, middle, mention_2, right, '
    'left_POS, mention_1_POS, middle_POS, mention_2_POS, right_POS')


class Corpus(object):
    def __init__(self, src_filename_or_examples):
        if isinstance(src_filename_or_examples, str):
            self.examples = self.read_examples(src_filename_or_examples)
        else:
            self.examples = src_filename_or_examples
        self.examples_by_entities = {}
        self._index_examples_by_entities()

    @staticmethod
    def read_examples(src_filename):
        examples = []
        with gzip.open(src_filename) as f:
            for line in f:
                fields = line[:-1].decode('utf-8').split('\t')
                examples.append(Example(*fields))
        return examples

    def _index_examples_by_entities(self):
        for ex in self.examples:
            if ex.entity_1 not in self.examples_by_entities:
                self.examples_by_entities[ex.entity_1] = {}
            if ex.entity_2 not in self.examples_by_entities[ex.entity_1]:
                self.examples_by_entities[ex.entity_1][ex.entity_2] = []
            self.examples_by_entities[ex.entity_1][ex.entity_2].append(ex)

    def get_examples_for_entities(self, e1, e2):
        try:
            return self.examples_by_entities[e1][e2]
        except KeyError:
            return []

    def show_examples_for_pair(self, e1, e2):
        exs = self.get_examples_for_entities(e1, e2)
        if exs:
            print('The first of {0:,} examples for {1:} and {2:} is:'.format(
                len(exs), e1, e2))
            print(exs[0])
        else:
            print('No examples for {0:} and {1:}'.format(e1, e2))

    def __str__(self):
        return 'Corpus with {0:,} examples'.format(len(self.examples))

    def __repr__(self):
        return str(self)

    def __len__(self):
        return len(self.examples)


KBTriple = namedtuple('KBTriple', 'rel, sbj, obj')


class KB(object):
    def __init__(self, src_filename_or_triples):
        if isinstance(src_filename_or_triples, str):
            self.kb_triples = self.read_kb_triples(src_filename_or_triples)
        else:
            self.kb_triples = src_filename_or_triples
        self.all_relations = []
        self.all_entity_pairs = []
        self.kb_triples_by_relation = {}
        self.kb_triples_by_entities = {}
        self._collect_all_entity_pairs()
        self._index_kb_triples_by_relation()
        self._index_kb_triples_by_entities()

    @staticmethod
    def read_kb_triples(src_filename):
        kb_triples = []
        with gzip.open(src_filename) as f:
            for line in f:
                rel, sbj, obj = line[:-1].decode('utf-8').split('\t')
                kb_triples.append(KBTriple(rel, sbj, obj))
        return kb_triples

    def _collect_all_entity_pairs(self):
        pairs = set()
        for kbt in self.kb_triples:
            pairs.add((kbt.sbj, kbt.obj))
        self.all_entity_pairs = sorted(list(pairs))

    def _index_kb_triples_by_relation(self):
        for kbt in self.kb_triples:
            if kbt.rel not in self.kb_triples_by_relation:
                self.kb_triples_by_relation[kbt.rel] = []
            self.kb_triples_by_relation[kbt.rel].append(kbt)
        self.all_relations = sorted(list(self.kb_triples_by_relation))

    def _index_kb_triples_by_entities(self):
        for kbt in self.kb_triples:
            if kbt.sbj not in self.kb_triples_by_entities:
                self.kb_triples_by_entities[kbt.sbj] = {}
            if kbt.obj not in self.kb_triples_by_entities[kbt.sbj]:
                self.kb_triples_by_entities[kbt.sbj][kbt.obj] = []
            self.kb_triples_by_entities[kbt.sbj][kbt.obj].append(kbt)

    def get_triples_for_relation(self, rel):
        try:
            return self.kb_triples_by_relation[rel]
        except KeyError:
            return []

    def get_triples_for_entities(self, e1, e2):
        try:
            return self.kb_triples_by_entities[e1][e2]
        except KeyError:
            return []

    def __str__(self):
        return 'KB with {0:,} triples'.format(len(self.kb_triples))

    def __repr__(self):
        return str(self)

    def __len__(self):
        return len(self.kb_triples)


class Dataset(object):
    def __init__(self, corpus, kb):
        self.corpus = corpus
        self.kb = kb

    def find_unrelated_pairs(self):
        unrelated_pairs = set()
        for ex in self.corpus.examples:
            if self.kb.get_triples_for_entities(ex.entity_1, ex.entity_2):
                continue
            if self.kb.get_triples_for_entities(ex.entity_2, ex.entity_1):
                continue
            unrelated_pairs.add((ex.entity_1, ex.entity_2))
            unrelated_pairs.add((ex.entity_2, ex.entity_1))
        return unrelated_pairs

    def featurize(self, kbts_by_rel, featurizers, vectorizer=None):
        # Create feature counters for all instances (kbts).
        feat_counters_by_rel = defaultdict(list)
        for rel, kbts in kbts_by_rel.items():
            for kbt in kbts:
                feature_counter = Counter()
                for featurizer in featurizers:
                    feature_counter = featurizer(kbt, self.corpus, feature_counter)
                feat_counters_by_rel[rel].append(feature_counter)
        feat_matrices_by_rel = defaultdict(list)
        # If we haven't been given a Vectorizer, create one and fit
        # it to all the feature counters.
        if vectorizer is None:
            vectorizer = DictVectorizer(sparse=True)
            def traverse_dicts():
                for dict_list in feat_counters_by_rel.values():
                    for d in dict_list:
                        yield d
            vectorizer.fit(traverse_dicts())
        # Now use the Vectorizer to transform feature dictionaries
        # into feature matrices.
        for rel, feat_counters in feat_counters_by_rel.items():
            feat_matrices_by_rel[rel] = vectorizer.transform(feat_counters)
        return feat_matrices_by_rel, vectorizer

    def build_dataset(self,
            include_positive=True,
            sampling_rate=0.1,
            seed=1):
        unrelated_pairs = self.find_unrelated_pairs()
        random.seed(seed)
        unrelated_pairs = random.sample(
            unrelated_pairs, int(sampling_rate * len(unrelated_pairs)))
        kbts_by_rel = defaultdict(list)
        labels_by_rel = defaultdict(list)
        for index, rel in enumerate(self.kb.all_relations):
            if include_positive:
                for kbt in self.kb.get_triples_for_relation(rel):
                    kbts_by_rel[rel].append(kbt)
                    labels_by_rel[rel].append(True)
            for sbj, obj in unrelated_pairs:
                kbts_by_rel[rel].append(KBTriple(rel, sbj, obj))
                labels_by_rel[rel].append(False)
        return kbts_by_rel, labels_by_rel

    def build_splits(self,
            split_names=['tiny', 'train', 'dev'],
            split_fracs=[0.01, 0.74, 0.25],
            seed=1):
        if len(split_names) != len(split_fracs):
            raise ValueError('split_names and split_fracs must be of equal length')
        if sum(split_fracs) != 1.0:
            raise ValueError('split_fracs must sum to 1')
        n = len(split_fracs) # for convenience only

        def split_list(xs):
            xs = sorted(xs) # sorted for reproducibility
            if seed:
                random.seed(seed)
            random.shuffle(xs)
            split_points = [0] + [int(round(frac * len(xs)))
                                  for frac in np.cumsum(split_fracs)]
            return [xs[split_points[i]:split_points[i + 1]] for i in range(n)]

        # first, split the entities that appear as subjects in the KB
        sbjs = list(set([kbt.sbj for kbt in self.kb.kb_triples]))
        sbj_splits = split_list(sbjs)
        sbj_split_dict = {sbj: i for i, split in enumerate(sbj_splits)
                                 for sbj in split}
        # next, split the KB triples based on their subjects
        kbt_splits = [[kbt for kbt in self.kb.kb_triples if sbj_split_dict[kbt.sbj] == i]
                      for i in range(n)]
        # now split examples based on the entities they contain
        ex_splits = [[] for i in range(n + 1)] # include an extra split
        for ex in self.corpus.examples:
            if ex.entity_1 in sbj_split_dict:
                # if entity_1 is a sbj in the KB, assign example to split of that sbj
                ex_splits[sbj_split_dict[ex.entity_1]].append(ex)
            elif ex.entity_2 in sbj_split_dict:
                # if entity_2 is a sbj in the KB, assign example to split of that sbj
                ex_splits[sbj_split_dict[ex.entity_2]].append(ex)
            else:
                # otherwise, put in extra split to be redistributed
                ex_splits[-1].append(ex)
        # reallocate the examples that weren't assigned to a split on first pass
        extra_ex_splits = split_list(ex_splits[-1])
        ex_splits = [ex_splits[i] + extra_ex_splits[i] for i in range(n)]

        # create a Corpus and a KB for each split
        data = {}
        for i in range(n):
            data[split_names[i]] = Dataset(Corpus(ex_splits[i]), KB(kbt_splits[i]))
        data['all'] = self
        return data

    def count_examples(self):
        counter = Counter()
        for rel in self.kb.all_relations:
            for kbt in self.kb.get_triples_for_relation(rel):
                # count examples in both forward and reverse directions
                counter[rel] += len(self.corpus.get_examples_for_entities(kbt.sbj, kbt.obj))
                counter[rel] += len(self.corpus.get_examples_for_entities(kbt.obj, kbt.sbj))
        # report results
        print('{:20s} {:>10s} {:>10s} {:>10s}'.format(
            '', '', '', 'examples'))
        print('{:20s} {:>10s} {:>10s} {:>10s}'.format(
            'relation', 'examples', 'triples', '/triple'))
        print('{:20s} {:>10s} {:>10s} {:>10s}'.format(
            '--------', '--------', '-------', '-------'))
        for rel in self.kb.all_relations:
            nx = counter[rel]
            nt = len(self.kb.get_triples_for_relation(rel))
            print('{:20s} {:10d} {:10d} {:10.2f}'.format(
                rel, nx, nt, 1.0 * nx / nt))

    def count_relation_combinations(self):
        counter = Counter()
        for sbj, obj in self.kb.all_entity_pairs:
            rels = tuple(sorted({kbt.rel for kbt in self.kb.get_triples_for_entities(sbj, obj)}))
            if len(rels) > 1:
                counter[rels] += 1
        counts = sorted([(count, key) for key, count in counter.items()], reverse=True)
        print('The most common relation combinations are:')
        for count, key in counts:
            print('{:10d} {}'.format(count, key))

    def __str__(self):
        return "{}; {}".format(self.corpus, self.kb)

    def __repr__(self):
        return str(self)


def print_statistics_header():
    print('{:20s} {:>10s} {:>10s} {:>10s} {:>10s} {:>10s}'.format(
        'relation', 'precision', 'recall', 'f-score', 'support', 'size'))
    print('{:20s} {:>10s} {:>10s} {:>10s} {:>10s} {:>10s}'.format(
        '-' * 18, '-' * 9, '-' * 9, '-' * 9, '-' * 9, '-' * 9))


def print_statistics_row(rel, result):
    print('{:20s} {:10.3f} {:10.3f} {:10.3f} {:10d} {:10d}'.format(rel, *result))


def print_statistics_footer(avg_result):
    print('{:20s} {:>10s} {:>10s} {:>10s} {:>10s} {:>10s}'.format(
        '-' * 18, '-' * 9, '-' * 9, '-' * 9, '-' * 9, '-' * 9))
    print('{:20s} {:10.3f} {:10.3f} {:10.3f} {:10d} {:10d}'.format('macro-average', *avg_result))


def macro_average_results(results):
    avg_result = [np.average([r[i] for r in results.values()]) for i in range(3)]
    avg_result.append(np.sum([r[3] for r in results.values()]))
    avg_result.append(np.sum([r[4] for r in results.values()]))
    return avg_result


def evaluate(splits, classifier, test_split='dev', verbose=True):
    test_kbts_by_rel, true_labels_by_rel = splits[test_split].build_dataset()
    results = {}
    if verbose:
        print_statistics_header()
    for rel in splits['all'].kb.all_relations:
        pred_labels = classifier(test_kbts_by_rel[rel])
        stats = precision_recall_fscore_support(true_labels_by_rel[rel], pred_labels, beta=0.5)
        stats = [stat[1] for stat in stats]  # stats[1] is the stat for label True
        stats.append(len(pred_labels)) # number of examples
        results[rel] = stats
        if verbose:
            print_statistics_row(rel, results[rel])
    avg_result = macro_average_results(results)
    if verbose:
        print_statistics_footer(avg_result)
    return avg_result[2]  # return f_0.5 score as summary statistic


def train_models(
        splits,
        featurizers,
        split_name='train',
        model_factory=lambda: LogisticRegression(fit_intercept=True, solver='liblinear'),
        verbose=True):
    train_dataset = splits[split_name]
    train_o, train_y = train_dataset.build_dataset()
    train_X, vectorizer = train_dataset.featurize(train_o, featurizers)
    models = {}
    for rel in splits['all'].kb.all_relations:
        models[rel] = model_factory()
        models[rel].fit(train_X[rel], train_y[rel])
    return {
        'featurizers': featurizers,
        'vectorizer': vectorizer,
        'models': models,
        'all_relations': splits['all'].kb.all_relations}


def predict(splits, train_result, split_name='dev'):
    assess_dataset = splits[split_name]
    assess_o, assess_y = assess_dataset.build_dataset()
    test_X, _ = assess_dataset.featurize(
        assess_o,
        featurizers=train_result['featurizers'],
        vectorizer=train_result['vectorizer'])
    predictions = {}
    for rel in train_result['all_relations']:
        predictions[rel] = train_result['models'][rel].predict(test_X[rel])
    return predictions, assess_y


def evaluate_predictions(predictions, test_y, verbose=True):
    results = {}  # one result row for each relation
    if verbose:
        print_statistics_header()
    for rel, preds in predictions.items():
        stats = precision_recall_fscore_support(test_y[rel], preds, beta=0.5)
        stats = [stat[1] for stat in stats]  # stats[1] is the stat for label True
        stats.append(len(test_y[rel]))
        results[rel] = stats
        if verbose:
            print_statistics_row(rel, results[rel])
    avg_result = macro_average_results(results)
    if verbose:
        print_statistics_footer(avg_result)
    return avg_result[2]  # return f_0.5 score as summary statistic


def experiment(
        splits,
        featurizers,
        train_split='train',
        test_split='dev',
        model_factory=lambda: LogisticRegression(fit_intercept=True, solver='liblinear'),
        verbose=True):
    train_result = train_models(
        splits,
        featurizers=featurizers,
        split_name=train_split,
        model_factory=model_factory,
        verbose=verbose)
    predictions, test_y = predict(
        splits,
        train_result,
        split_name=test_split)
    evaluate_predictions(
        predictions,
        test_y,
        verbose)
    return train_result


def examine_model_weights(train_result, k=3, verbose=True):
    feature_names = train_result['vectorizer'].get_feature_names()
    for rel, model in train_result['models'].items():
        print('Highest and lowest feature weights for relation {}:\n'.format(rel))
        sorted_weights = sorted([(wgt, idx) for idx, wgt in enumerate(model.coef_[0])], reverse=True)
        for wgt, idx in sorted_weights[:k]:
            print('{:10.3f} {}'.format(wgt, feature_names[idx]))
        print('{:>10s} {}'.format('.....', '.....'))
        for wgt, idx in sorted_weights[-k:]:
            print('{:10.3f} {}'.format(wgt, feature_names[idx]))
        print()


def find_new_relation_instances(
        dataset,
        featurizers,
        train_split='train',
        test_split='dev',
        model_factory=lambda: LogisticRegression(fit_intercept=True, solver='liblinear'),
        k=10,
        verbose=True):
    splits = dataset.build_splits()
    # train models
    train_result = train_models(
        splits,
        split_name=train_split,
        featurizers=featurizers,
        model_factory=model_factory,
        verbose=True)
    test_split = splits[test_split]
    neg_o, neg_y = test_split.build_dataset(
        include_positive=False,
        sampling_rate=1.0)
    neg_X, _ = test_split.featurize(
        neg_o,
        featurizers=featurizers,
        vectorizer=train_result['vectorizer'])
    # Report highest confidence predictions:
    for rel, model in train_result['models'].items():
        print('Highest probability examples for relation {}:\n'.format(rel))
        probs = model.predict_proba(neg_X[rel])
        probs = [prob[1] for prob in probs] # probability for class True
        sorted_probs = sorted([(p, idx) for idx, p in enumerate(probs)], reverse=True)
        for p, idx in sorted_probs[:k]:
            print('{:10.3f} {}'.format(p, neg_o[rel][idx]))
        print()


def bake_off_experiment(train_result, rel_ext_data_home, verbose=True):
    test_corpus_filename = os.path.join(rel_ext_data_home, "corpus-test.tsv.gz")
    test_kb_filename = os.path.join(rel_ext_data_home, "kb-test.tsv.gz")
    corpus = Corpus(test_corpus_filename)
    kb = KB(test_kb_filename)
    test_dataset = Dataset(corpus, kb)
    test_o, test_y = test_dataset.build_dataset()
    test_X, _ = test_dataset.featurize(
        test_o,
        featurizers=train_result['featurizers'],
        vectorizer=train_result['vectorizer'])
    predictions = {}
    for rel in train_result['all_relations']:
        predictions[rel] = train_result['models'][rel].predict(test_X[rel])
    evaluate_predictions(
        predictions,
        test_y,
        verbose=verbose)
