"""news/pairs_tune: sample → request files → replies → report, on a
synthetic store with one straddled boundary."""
import csv
import glob
import os
import shutil
import tempfile
import unittest

from scripts.errors import PipelineError
from scripts.news import pairs_tune
from scripts.news import paths
from tests.mt.test_run import AMIS, Store

NAME = "20210201_032_晚間_Amis_阿美"


class TestTune(Store):
    def setUp(self):
        super().setUp()
        self.standard()
        # two neighbouring segments; subtitle 2 (24–28 s) lies 1 s in the
        # first and 3 s in the second: 25%, bucket 20–30
        path = paths.stage_path(paths.SAPOLITA_SRT, NAME, ".srt")
        with open(path, "w", encoding="utf-8") as handle:
            handle.write("1\n00:00:19,500 --> 00:00:25,000\n族語：%s\n"
                         "華語：奇美部落的道路\n\n2\n00:00:25,000 --> "
                         "00:00:28,200\n族語：o salikaka no kalingko a "
                         "matini\n華語：花蓮縣的族人\n" % AMIS)
        self.work = tempfile.mkdtemp(prefix="tune-")
        self.addCleanup(shutil.rmtree, self.work, True)

    def requests(self):
        return sorted(glob.glob(os.path.join(self.work, "request-*.tsv")))

    def test_sample_writes_merged_and_split_to_separate_batches(self):
        pairs_tune.write_sample(self.work, per_bucket=5, seed=1)
        with open(os.path.join(self.work, "sample.csv"),
                  encoding="utf-8") as handle:
            rows = list(csv.DictReader(handle))
        self.assertEqual(sorted(r["版本"] for r in rows), ["A", "B", "G"])
        self.assertEqual({r["格"] for r in rows}, {"2"})
        batch_of = {}
        for path in self.requests():
            number = os.path.basename(path).split("-")[1]
            with open(path, encoding="utf-8") as handle:
                for line in list(handle)[1:]:
                    batch_of[line.split("\t")[0]] = number
        kinds = {}
        for row in rows:
            kinds.setdefault(batch_of[row["編號"]], set()).add(
                "G" if row["版本"] == "G" else "AB")
        for found in kinds.values():
            self.assertEqual(len(found), 1)

    def test_ingest_then_report(self):
        pairs_tune.write_sample(self.work, per_bucket=5, seed=1)
        with open(os.path.join(self.work, "sample.csv"),
                  encoding="utf-8") as handle:
            rows = list(csv.DictReader(handle))
        label = {"G": "高", "A": "低", "B": "低"}
        numbers = sorted({os.path.basename(p).split("-")[1]
                          for p in self.requests()})
        for number in numbers:
            ids = pairs_tune.request_ids(self.work, number)
            with open(os.path.join(self.work, "reply-%s.tsv" % number), "w",
                      encoding="utf-8") as handle:
                for row in rows:
                    if int(row["編號"]) in ids:
                        handle.write("%s\t%s\t理由\n"
                                     % (row["編號"], label[row["版本"]]))
            pairs_tune.accept(self.work, number)
        table, chosen = pairs_tune.report(self.work)
        by = {}
        for row in table:
            by[row["格"]] = row
        self.assertEqual(by["20–30%"]["合併較好"], 1)
        self.assertEqual(by["20–30%"]["判定"], "分不出")

    def test_short_reply_is_refused_and_not_accepted(self):
        pairs_tune.write_sample(self.work, per_bucket=5, seed=1)
        number = os.path.basename(self.requests()[0]).split("-")[1]
        with open(os.path.join(self.work, "reply-%s.tsv" % number), "w",
                  encoding="utf-8") as handle:
            handle.write("")
        with self.assertRaises(PipelineError):
            pairs_tune.accept(self.work, number)
        self.assertFalse(os.path.exists(os.path.join(
            self.work, "accepted", "reply-%s.tsv" % number)))


if __name__ == "__main__":
    unittest.main()
