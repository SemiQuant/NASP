"""
The purpose of these tests is to ensure commands are properly shell escaped.

Characters that cause problems include pipes: '|', redirects: '>', newlines: '\n', etc
"""
__author__ = 'jtravis'

import unittest
from unittest.mock import Mock, call
from collections import namedtuple
#import os
import itertools
#from tempfile import TemporaryDirectory

from nasp import dispatcher

# TODO: @unittest.skipUnless(termios, 'tests require system with termios')

App = namedtuple('App', ['name', 'path', 'args', 'job_params'])
Assembly = namedtuple('Assembly', ['name', 'read1', 'read2'])


class DispatcherShellEscapeCommandsTestCase(unittest.TestCase):
    maxDiff = None

    @classmethod
    def setUpClass(cls):
        pass

    def setUp(self):
        # Monkey-patch mock _submit_job function
        # Each call to submit_job will return an incrementing "job_id"
        self.mock_submit_job = Mock(side_effect=(str(n) for n in itertools.count(start=1, step=1)))
        self.mock_release_hold = Mock()
        dispatcher._submit_job = self.mock_submit_job
        dispatcher._release_hold = self.mock_release_hold

        self.assemblies = {
            'paired_basic': Assembly('NA10831_ATCACG_L002', 'NA10831_ATCACG_L002_R1_001.fastq.gz', 'NA10831_ATCACG_L002_R2_001.fastq.gz'),
            'paired_pipe': Assembly('NA|10831_ATCACG_L002', 'NA|10831_ATCACG_L002_R1_001.fastq.gz', 'NA|10831_ATCACG_L002_R2_001.fastq.gz'),
            'single_basic': Assembly('NA10831_ATCACG_L002', 'NA10831_ATCACG_L002.fastq.gz', ''),
            'single_pipe': Assembly('NA|10831_ATCACG_L002', 'NA|10831_ATCACG_L002.fastq.gz', ''),
        }

        self.job_params = {
            'name': 'test|job|name',
            'num_cpus': 2,
            'mem_requested': 4,
            'walltime': 6,
            'queue': 'test|queue',
            'args': '--fake-job-parameter -f |ake -j o|b -p arameter|',
            'work_dir': 'test|work|dir',
        }

        self.samtools = App('samtools', '/path/to/samtools', '', {})
        self.job_submitter = 'pbs'
        self.reference = 'reference.fasta'
        self.output_folder = 'output_folder'
        self.index_job_id = ('jobid', 'action')

        self.bam = '/path/to/test-fake-aligner.bam'

        self.aligners = {
            'bwamem': App('bwamem', '/path/to/bwa', '-x "-k17 -W40 -r10 -A1 -B1 -O1 -E1 -L0"', self.job_params),
            'bwa': App('bwa', '/path/to/bwa', '-x "-k17 -W40 -r10 -A1 -B1 -O1 -E1 -L0"', self.job_params),
            'bowtie2': App('bowtie2', '/path/to/bowtie2', '--very-sensitive-local --un pipe|in|name.fastq.gz --al "space in name.fastq.gz"', self.job_params),
            'novoalign': App('novoalign', '/path/to/novoalign', '-K mismatch:stats.txt -i MP 99-99 99,99', self.job_params),
            'snap': App('snap', '/path/to/snap', '--TODO', self.job_params),
        }

        self.snpcallers = {
            'gatk': App('gatk', '/path/to/gatk', '--TODO', self.job_params) ,
            'solsnp': App('solsnp', '/path/to/solsnp', '--TODO', self.job_params) 
        }


    def tearDown(self):
        pass

    def test_samtools_view_sort_index_pipe_command(self):
        tests = {
            'paired_basic': "/path/to/samtools view -S -b -h - | /path/to/samtools sort - NA10831_ATCACG_L002; /path/to/samtools index NA10831_ATCACG_L002.bam",

            'paired_pipe': "/path/to/samtools view -S -b -h - | /path/to/samtools sort - 'NA|10831_ATCACG_L002'; /path/to/samtools index 'NA|10831_ATCACG_L002.bam'",
        }

        for sample_type, expect in tests.items():
            result = dispatcher._samtools_view_sort_index_pipe_command(self.samtools.path, self.assemblies[sample_type].name)
            self.assertEqual(expect, result)


    def test_bwamem_command(self):
        tests = {
            'paired_basic': "/path/to/bwa mem -R '@RG\\tID:NA10831_ATCACG_L002\\tSM:NA10831_ATCACG_L002' -x '-k17 -W40 -r10 -A1 -B1 -O1 -E1 -L0' -t 2 reference.fasta NA10831_ATCACG_L002_R1_001.fastq.gz NA10831_ATCACG_L002_R2_001.fastq.gz",

            'paired_pipe': "/path/to/bwa mem -R '@RG\\tID:NA|10831_ATCACG_L002\\tSM:NA|10831_ATCACG_L002' -x '-k17 -W40 -r10 -A1 -B1 -O1 -E1 -L0' -t 2 reference.fasta 'NA|10831_ATCACG_L002_R1_001.fastq.gz' 'NA|10831_ATCACG_L002_R2_001.fastq.gz'",

            'single_basic': "/path/to/bwa mem -R '@RG\\tID:NA10831_ATCACG_L002\\tSM:NA10831_ATCACG_L002' -x '-k17 -W40 -r10 -A1 -B1 -O1 -E1 -L0' -t 2 reference.fasta NA10831_ATCACG_L002.fastq.gz ",

            'single_pipe': "/path/to/bwa mem -R '@RG\\tID:NA|10831_ATCACG_L002\\tSM:NA|10831_ATCACG_L002' -x '-k17 -W40 -r10 -A1 -B1 -O1 -E1 -L0' -t 2 reference.fasta 'NA|10831_ATCACG_L002.fastq.gz' "
        }

        bwamem = self.aligners['bwamem']
        ncpu = bwamem.job_params['num_cpus']

        for sample_type, expect in tests.items():
            result = dispatcher._bwamem_command(bwamem.path, bwamem.args, ncpu, self.reference, *self.assemblies[sample_type])
            self.assertEqual(expect, result)


    def test_bwa_command(self):
        tests = {
            'paired_basic': "/path/to/bwa aln  reference.fasta NA10831_ATCACG_L002_R1_001.fastq.gz -t 2 -f output_folder/bwa/NA10831_ATCACG_L002-R1.sai -x '-k17 -W40 -r10 -A1 -B1 -O1 -E1 -L0'; /path/to/bwa aln  reference.fasta NA10831_ATCACG_L002_R2_001.fastq.gz -t 2 -f output_folder/bwa/NA10831_ATCACG_L002-R1.sai -x '-k17 -W40 -r10 -A1 -B1 -O1 -E1 -L0'; /path/to/bwa sampe -r '@RG\\tID:NA10831_ATCACG_L002\\tSM:NA10831_ATCACG_L002' reference.fasta output_folder/bwa/NA10831_ATCACG_L002-R1.sai output_folder/bwa/NA10831_ATCACG_L002-R2.sai NA10831_ATCACG_L002_R1_001.fastq.gz NA10831_ATCACG_L002_R2_001.fastq.gz -x '-k17 -W40 -r10 -A1 -B1 -O1 -E1 -L0'",

            'paired_pipe': "/path/to/bwa aln  reference.fasta 'NA|10831_ATCACG_L002_R1_001.fastq.gz' -t 2 -f 'output_folder/bwa/NA|10831_ATCACG_L002-R1.sai' -x '-k17 -W40 -r10 -A1 -B1 -O1 -E1 -L0'; /path/to/bwa aln  reference.fasta 'NA|10831_ATCACG_L002_R2_001.fastq.gz' -t 2 -f 'output_folder/bwa/NA|10831_ATCACG_L002-R1.sai' -x '-k17 -W40 -r10 -A1 -B1 -O1 -E1 -L0'; /path/to/bwa sampe -r '@RG\\tID:NA|10831_ATCACG_L002\\tSM:NA|10831_ATCACG_L002' reference.fasta 'output_folder/bwa/NA|10831_ATCACG_L002-R1.sai' 'output_folder/bwa/NA|10831_ATCACG_L002-R2.sai' 'NA|10831_ATCACG_L002_R1_001.fastq.gz' 'NA|10831_ATCACG_L002_R2_001.fastq.gz' -x '-k17 -W40 -r10 -A1 -B1 -O1 -E1 -L0'",

            'single_basic': "/path/to/bwa aln  reference.fasta NA10831_ATCACG_L002.fastq.gz -t 2 -f output_folder/bwa/NA10831_ATCACG_L002.sai -x '-k17 -W40 -r10 -A1 -B1 -O1 -E1 -L0'; /path/to/bwa samse -r '@RG\\tID:NA10831_ATCACG_L002\\tSM:NA10831_ATCACG_L002' reference.fasta output_folder/bwa/NA10831_ATCACG_L002.sai NA10831_ATCACG_L002.fastq.gz -x '-k17 -W40 -r10 -A1 -B1 -O1 -E1 -L0'",

            'single_pipe': "/path/to/bwa aln  reference.fasta 'NA|10831_ATCACG_L002.fastq.gz' -t 2 -f 'output_folder/bwa/NA|10831_ATCACG_L002.sai' -x '-k17 -W40 -r10 -A1 -B1 -O1 -E1 -L0'; /path/to/bwa samse -r '@RG\\tID:NA|10831_ATCACG_L002\\tSM:NA|10831_ATCACG_L002' reference.fasta 'output_folder/bwa/NA|10831_ATCACG_L002.sai' 'NA|10831_ATCACG_L002.fastq.gz' -x '-k17 -W40 -r10 -A1 -B1 -O1 -E1 -L0'"
        }

        bwa = self.aligners['bwa']
        ncpu = bwa.job_params['num_cpus']

        for sample_type, expect in tests.items():
            result = dispatcher._bwa_command(bwa.path, bwa.args, ncpu, self.reference, self.output_folder, *self.assemblies[sample_type])
            self.assertEqual(expect, result)


    def test_bowtie2_command(self):
        tests = {
            'paired_basic': "/path/to/bowtie2 --very-sensitive-local --un 'pipe|in|name.fastq.gz' --al 'space in name.fastq.gz' --threads 2 --rg SM:NA10831_ATCACG_L002 --rg-id NA10831_ATCACG_L002 -x reference -1 NA10831_ATCACG_L002_R1_001.fastq.gz -2 NA10831_ATCACG_L002_R2_001.fastq.gz",

            'paired_pipe': "/path/to/bowtie2 --very-sensitive-local --un 'pipe|in|name.fastq.gz' --al 'space in name.fastq.gz' --threads 2 --rg 'SM:NA|10831_ATCACG_L002' --rg-id 'NA|10831_ATCACG_L002' -x reference -1 'NA|10831_ATCACG_L002_R1_001.fastq.gz' -2 'NA|10831_ATCACG_L002_R2_001.fastq.gz'",

            'single_basic': "/path/to/bowtie2 --very-sensitive-local --un 'pipe|in|name.fastq.gz' --al 'space in name.fastq.gz' --threads 2 --rg SM:NA10831_ATCACG_L002 --rg-id NA10831_ATCACG_L002 -x reference -U NA10831_ATCACG_L002.fastq.gz",

            'single_pipe': "/path/to/bowtie2 --very-sensitive-local --un 'pipe|in|name.fastq.gz' --al 'space in name.fastq.gz' --threads 2 --rg 'SM:NA|10831_ATCACG_L002' --rg-id 'NA|10831_ATCACG_L002' -x reference -U 'NA|10831_ATCACG_L002.fastq.gz'"
        }

        bowtie2 = self.aligners['bowtie2']
        ncpu = bowtie2.job_params['num_cpus']

        for sample_type, expect in tests.items():
            result = dispatcher._bowtie2_command(bowtie2.path, bowtie2.args, ncpu, self.reference, *self.assemblies[sample_type])
            self.assertEqual(expect, result)


    def test_novoalign_command(self):
        tests = {
            'paired_basic': "/path/to/novoalign -d reference.fasta.idx -f NA10831_ATCACG_L002_R1_001.fastq.gz NA10831_ATCACG_L002_R2_001.fastq.gz -i PE 500,100 -c 2 -o SAM '@RG\\tID:NA10831_ATCACG_L002\\tSM:NA10831_ATCACG_L002' -K mismatch:stats.txt -i MP 99-99 99,99",

            'paired_pipe': "/path/to/novoalign -d reference.fasta.idx -f 'NA|10831_ATCACG_L002_R1_001.fastq.gz' 'NA|10831_ATCACG_L002_R2_001.fastq.gz' -i PE 500,100 -c 2 -o SAM '@RG\\tID:NA|10831_ATCACG_L002\\tSM:NA|10831_ATCACG_L002' -K mismatch:stats.txt -i MP 99-99 99,99",

            'single_basic': "/path/to/novoalign -d reference.fasta.idx -f NA10831_ATCACG_L002.fastq.gz   -c 2 -o SAM '@RG\\tID:NA10831_ATCACG_L002\\tSM:NA10831_ATCACG_L002' -K mismatch:stats.txt -i MP 99-99 99,99",

            'single_pipe': "/path/to/novoalign -d reference.fasta.idx -f 'NA|10831_ATCACG_L002.fastq.gz'   -c 2 -o SAM '@RG\\tID:NA|10831_ATCACG_L002\\tSM:NA|10831_ATCACG_L002' -K mismatch:stats.txt -i MP 99-99 99,99",
        }

        novoalign = self.aligners['novoalign']
        ncpu = novoalign.job_params['num_cpus']

        for sample_type, expect in tests.items():
            result = dispatcher._novoalign_command(novoalign.path, novoalign.args, ncpu, self.reference, *self.assemblies[sample_type])
            self.assertEqual(expect, result)


    def test_snap_command(self):
        tests = {
            'paired_basic': "/path/to/snap paired output_folder/reference/snap NA10831_ATCACG_L002_R1_001.fastq.gz NA10831_ATCACG_L002_R2_001.fastq.gz -t 2 -b --TODO -o sam -",

            'paired_pipe': "/path/to/snap paired output_folder/reference/snap 'NA|10831_ATCACG_L002_R1_001.fastq.gz' 'NA|10831_ATCACG_L002_R2_001.fastq.gz' -t 2 -b --TODO -o sam -",

            'single_basic': "/path/to/snap single output_folder/reference/snap NA10831_ATCACG_L002.fastq.gz  -t 2 -b --TODO -o sam -",

            'single_pipe': "/path/to/snap single output_folder/reference/snap 'NA|10831_ATCACG_L002.fastq.gz'  -t 2 -b --TODO -o sam -",
        }

        snap = self.aligners['snap']
        ncpu = snap.job_params['num_cpus']

        for sample_type, expect in tests.items():
            result = dispatcher._snap_command(snap.path, snap.args, ncpu, self.reference, self.output_folder, *self.assemblies[sample_type])
            self.assertEqual(expect, result)


    def test_align_reads_bowtie2(self):
        configuration = {
            'job_submitter': self.job_submitter,
            'aligners': [ self.aligners['bowtie2'] ],
            'samtools': self.samtools,
            'output_folder': self.output_folder
        }

        expected_submit_job_calls = [
            call(
                'pbs',
                "/path/to/bowtie2 --very-sensitive-local --un 'pipe|in|name.fastq.gz' --al 'space in name.fastq.gz' --threads 2 --rg 'SM:NA|10831_ATCACG_L002' --rg-id 'NA|10831_ATCACG_L002' -x reference -1 'NA|10831_ATCACG_L002_R1_001.fastq.gz' -2 'NA|10831_ATCACG_L002_R2_001.fastq.gz'",
                {'work_dir': 'output_folder/bowtie2', 'queue': 'test|queue', 'name': 'nasp_bowtie2_NA|10831_ATCACG_L002', 'args': '--fake-job-parameter -f |ake -j o|b -p arameter|', 'walltime': 6, 'mem_requested': 4, 'num_cpus': 2},
                (('jobid', 'action'),)
            ),
        ]

        dispatcher._align_reads(self.assemblies['paired_pipe'], configuration, self.index_job_id, self.reference)
        dispatcher._submit_job.assert_has_calls(expected_submit_job_calls)


    def test_align_reads_bwa(self):
        configuration = {
            'job_submitter': self.job_submitter,
            'aligners': [ self.aligners['bwa'] ],
            'samtools': self.samtools,
            'output_folder': self.output_folder
        }

        expected_submit_job_calls = [
            call(
                'pbs',
                "/path/to/bwa aln  reference.fasta 'NA|10831_ATCACG_L002_R1_001.fastq.gz' -t 2 -f 'output_folder/bwa/NA|10831_ATCACG_L002-R1.sai' -x '-k17 -W40 -r10 -A1 -B1 -O1 -E1 -L0'; /path/to/bwa aln  reference.fasta 'NA|10831_ATCACG_L002_R2_001.fastq.gz' -t 2 -f 'output_folder/bwa/NA|10831_ATCACG_L002-R1.sai' -x '-k17 -W40 -r10 -A1 -B1 -O1 -E1 -L0'; /path/to/bwa sampe -r '@RG\\tID:NA|10831_ATCACG_L002\\tSM:NA|10831_ATCACG_L002' reference.fasta 'output_folder/bwa/NA|10831_ATCACG_L002-R1.sai' 'output_folder/bwa/NA|10831_ATCACG_L002-R2.sai' 'NA|10831_ATCACG_L002_R1_001.fastq.gz' 'NA|10831_ATCACG_L002_R2_001.fastq.gz' -x '-k17 -W40 -r10 -A1 -B1 -O1 -E1 -L0'",
                {'args': '--fake-job-parameter -f |ake -j o|b -p arameter|', 'work_dir': 'output_folder/bwa', 'queue': 'test|queue', 'num_cpus': 2, 'name': 'nasp_bwa_NA|10831_ATCACG_L002', 'mem_requested': 4, 'walltime': 6},
                (('jobid', 'action'),)
            )
        ]

        dispatcher._align_reads(self.assemblies['paired_pipe'], configuration, self.index_job_id, self.reference)
        dispatcher._submit_job.assert_has_calls(expected_submit_job_calls)


    def test_align_reads_bwamem(self):
        configuration = {
            'job_submitter': self.job_submitter,
            'aligners': [ self.aligners['bwamem'] ],
            'samtools': self.samtools,
            'output_folder': self.output_folder
        }

        expected_submit_job_calls = [
            call(
                'pbs',
                "/path/to/bwa mem -R '@RG\\tID:NA|10831_ATCACG_L002\\tSM:NA|10831_ATCACG_L002' -x '-k17 -W40 -r10 -A1 -B1 -O1 -E1 -L0' -t 2 reference.fasta 'NA|10831_ATCACG_L002_R1_001.fastq.gz' 'NA|10831_ATCACG_L002_R2_001.fastq.gz'",
                {'work_dir': 'output_folder/bwamem', 'queue': 'test|queue', 'name': 'nasp_bwamem_NA|10831_ATCACG_L002', 'args': '--fake-job-parameter -f |ake -j o|b -p arameter|', 'walltime': 6, 'mem_requested': 4, 'num_cpus': 2},
                (('jobid', 'action'),)
            ),
        ]

        dispatcher._align_reads(self.assemblies['paired_pipe'], configuration, self.index_job_id, self.reference)
        dispatcher._submit_job.assert_has_calls(expected_submit_job_calls)


    def test_align_reads_novoalign(self):
        configuration = {
            'job_submitter': self.job_submitter,
            'aligners': [ self.aligners['novoalign'] ],
            'samtools': self.samtools,
            'output_folder': self.output_folder
        }

        expected_submit_job_calls = [
            call(
                'pbs',
                "/path/to/novoalign -d reference.fasta.idx -f 'NA|10831_ATCACG_L002_R1_001.fastq.gz' 'NA|10831_ATCACG_L002_R2_001.fastq.gz' -i PE 500,100 -c 2 -o SAM '@RG\\tID:NA|10831_ATCACG_L002\\tSM:NA|10831_ATCACG_L002' -K mismatch:stats.txt -i MP 99-99 99,99",
                {'name': 'nasp_novo_NA|10831_ATCACG_L002', 'queue': 'test|queue', 'mem_requested': 4, 'walltime': 6, 'num_cpus': 2, 'work_dir': 'output_folder/novo', 'args': '--fake-job-parameter -f |ake -j o|b -p arameter|'},
                (('jobid', 'action'),)
            )
        ]

        dispatcher._align_reads(self.assemblies['paired_pipe'], configuration, self.index_job_id, self.reference)
        dispatcher._submit_job.assert_has_calls(expected_submit_job_calls)


    def test_align_reads_snap(self):
        configuration = {
            'job_submitter': self.job_submitter,
            'aligners': [ self.aligners['snap'] ],
            'samtools': self.samtools,
            'output_folder': self.output_folder
        }

        expected_submit_job_calls = [
            call(
                'pbs',
                "/path/to/snap paired output_folder/reference/snap 'NA|10831_ATCACG_L002_R1_001.fastq.gz' 'NA|10831_ATCACG_L002_R2_001.fastq.gz' -t 2 -b --TODO -o sam -",
                {'walltime': 6, 'args': '--fake-job-parameter -f |ake -j o|b -p arameter|', 'num_cpus': 2, 'name': 'nasp_snap_NA|10831_ATCACG_L002', 'queue': 'test|queue', 'mem_requested': 4, 'work_dir': 'output_folder/snap'},
                (('jobid', 'action'),)
            )
        ]

        dispatcher._align_reads(self.assemblies['paired_pipe'], configuration, self.index_job_id, self.reference)
        dispatcher._submit_job.assert_has_calls(expected_submit_job_calls)


    def test_gatk_command(self):
        gatk = self.snpcallers['gatk']
        ncpu = gatk.job_params['num_cpus']
        mem = gatk.job_params['mem_requested']
        expect = 'java -Xmx4G -jar /path/to/gatk -T UnifiedGenotyper -dt NONE -glm BOTH -I /path/to/test-fake-aligner.bam -R reference.fasta -nt 2 -o /path/to/test-fake-aligner-gatk.vcf -out_mode EMIT_ALL_CONFIDENT_SITES -baq RECALCULATE --TODO'
        result = dispatcher._gatk_command(gatk.path, gatk.args, ncpu, mem, self.reference, self.bam)
        self.assertEqual(expect, result)


    def test_solsnp_command(self):
        solsnp = self.snpcallers['solsnp']
        ncpu = solsnp.job_params['num_cpus']
        mem = solsnp.job_params['mem_requested']
        expect = 'java -Xmx4G -jar /path/to/solsnp INPUT=/path/to/test-fake-aligner.bam REFERENCE_SEQUENCE=reference.fasta OUTPUT=/path/to/test-fake-aligner-solsnp.vcf SUMMARY=true CALCULATE_ALLELIC_BALANCE=true MINIMUM_COVERAGE=1 PLOIDY=Haploid STRAND_MODE=None OUTPUT_FORMAT=VCF OUTPUT_MODE=AllCallable --TODO'
        result = dispatcher._solsnp_command(solsnp.path, solsnp.args, ncpu, mem, self.reference, self.bam)
        self.assertEqual(expect, result)


    def test_varscan_command(self):
        expect = ''
        result = dispatcher._varscan_command()
        self.assertEqual(expect, result)


    def test_pbs_command(self):
        expect = "qsub -V -d 'test|work|dir' -w 'test|work|dir' -l ncpus=2,mem=4gb,walltime=6:00:00 -m a -N 'test|job|name' -q 'test|queue' --fake-job-parameter -f '|ake' -j 'o|b' -p 'arameter|'"
        result = dispatcher._pbs_command(**self.job_params)
        self.assertEqual(expect, result)


    def test_slurm_command(self):
        expect = "sbatch -D 'test|work|dir' -c 2 --mem=4000 --time=6:00:00 --mail-type=FAIL -J 'test|job|name' -p 'test|queue' --fake-job-parameter -f '|ake' -j 'o|b' -p 'arameter|'"
        result = dispatcher._slurm_command(**self.job_params)
        self.assertEqual(expect, result)

