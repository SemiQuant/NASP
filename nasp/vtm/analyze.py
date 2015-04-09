"""
TODO: more detail
The analyze module takes a collection of SampleAnalyses.
"""

__author__ = 'jtravis'

from collections import namedtuple, Counter
import itertools

# PositionInfo is all the data collected for a single position across all the SampleAnalyses.
PositionInfo = namedtuple('PositionInfo', [
    # True if all samples called A/C/G/T
    'is_all_called',
    'is_reference_clean',
    # True if reference call is in a duplicated region.
    'is_reference_duplicated',
    'is_all_passed_coverage',
    'is_all_passed_proportion',
    # True if all sample calls match.
    'is_all_passed_consensus',
    'is_all_quality_breadth',
    # True if all sample calls differ from the reference and passed all the filters (coverage, proportion, consensus).
    'is_best_snp',

    'all_sample_stats',

    'is_missing_matrix',

    # Count of sample calls that match the reference.
    'called_reference',
    'called_snp',
    'passed_coverage_filter',
    'passed_proportion_filter',
    'num_A',
    'num_C',
    'num_G',
    'num_T',
    'num_N',

    # Used in master / bestsnp matrix
    'call_str',
    # Used in missingdata matrix
    'masked_call_str',
    'CallWasMade',
    'PassedDepthFilter',
    'PassedProportionFilter',
    'Pattern'
])


class GenomeAnalysis:

    def __init__(self, coverage_threshold, proportion_threshold):
        """
        GenomeAnalysis collects statistics across a collection of SampleAnalyses relative to a reference SampleAnalysis.

        Args:
            coverage_threshold (int): Minimum coverage threshold for a sample position to be considered significant.
            proportion_threshold (int): Minimum proportion threshold for a sample position to be considered significant.
        """
        self._coverage_threshold = coverage_threshold
        self._proportion_threshold = proportion_threshold

    @staticmethod
    def sample_positions(contig_name, sample_groups):
        """
        sample_positions is a generator that yields positions across all the SampleAnalyses
        for the given contig grouped by sample name. This is the magic sauce that allows all
        the files to be read in unison as if they were a single file.

        TODO: Add See Also section referencing SampleAnalysis.

        Args:
            contig_name (str): Name of a contig from the reference.
            sample_groups (tuple of SampleAnalysis tuples):

        Return:
            tuple of Position tuples generator: Yields tuples of Position grouped by sample name.

        Example:

            sample_groups is the SampleAnalyses grouped by the name of the sample they are analyzing.

            +------------------------------------------------------------------------------------+
            |              Sample Group                |             Sample Group                |
            +==========================================+=========================================+
            |  SampleAnalysis    | SampleAnalysis      |  SampleAnalysis   | SampleAnalysis      |
            +------------------------------------------+-----------------------------------------+

            contig_groups is a mirror of sample_groups with each SampleAnalysis replaced
            with a contig position generator corresponding to the reference contig.

            +------------------------------------------------------------------------------------+
            |              Sample Group                |              Sample Group               |
            +==========================================+=========================================+
            | <contig_positions> | <contig_positions>  | <contig_positions> | <contig_positions> |
            +------------------------------------------+-----------------------------------------+

            The sample positions generator yields a tuple of Position tuples:
            ( (SampleInfo, SampleInfo,), (SampleInfo, SampleInfo), )

            +------------------------------------------------------------------------------------+
            |              Sample Group                |              Sample Group               |
            +==========================================+=========================================+
            | Position           | Position            | Position           | Position           |
            +------------------------------------------+-----------------------------------------+

            The order or Positions matching the order of SampleAnalyses is how we know which Position
            belongs to which SampleAnalysis.
        """
        # sample_groups is converted to contig_groups by calling get_contig() on each SampleAnalysis.
        contig_groups = tuple(
            tuple(map(lambda sample_analysis: sample_analysis.get_contig(contig_name).positions, sample_group)) \
            for sample_group in sample_groups
        )

        while True:
            # The inner tuple is all the sample analyses for a single sample.
            # The outer tuple is all the sample groupings.
            # ( (SampleInfo, SampleInfo,), (SampleInfo, SampleInfo), )
            yield tuple(tuple(map(next, contig_group)) for contig_group in contig_groups)

    @staticmethod
    def _is_pass_filter(value, threshold):
        """
        _filter determines if a position passed/failed the coverage/proportion filter.

        Args:
            value (int or str): coverage/proportion value from the file parser.
            threshold (int): The minimum value that will pass.

        Returns:
            (bool, str) True if it passed and a character representing the reason it passed/failed.
        """
        if value == '-':
            # Cannot determine due to no value specified. Assume it passed.
            # Always the case for Fasta files, sometimes the case for VCF.
            return True, '-'
        if value == '?':
            # Missing VCF position.
            return False, '?'
        if value >= threshold:
            # PASS - value is greater than threshold
            return True, 'Y'
        # FAIL - value is less than threshold
        return False, 'N'

    def analyze_position(self, reference_position, dups_position, samples):
        """
        analyze_position compares all the SampleAnalyses at a single position.

        Args:
            reference_position (Position): A single position from the reference genome.
            dups_position (Position): A single position from the duplicates file which indicates if the reference is in a duplicate region.
            samples (tuple of tuples of Position): A single position across all SampleAnalyses grouped by sample name.

        Returns:
            PositionInfo: All the information gathered
        """
        coverage_threshold = self._coverage_threshold
        proportion_threshold = self._proportion_threshold

        # General Stats
        # Assume true until proven otherwise.
        is_reference_clean = reference_position.simple_call != 'N'
        is_reference_duplicated = dups_position.call == '1'
        is_all_called = True
        is_all_passed_coverage = True
        is_all_passed_proportion = True
        # A sample has position consensus if:
        # - All analyses called and pass coverage/proportion filters.
        # - All analyses for the same sample match. Two analyses for the same position may differ if they belong to different samples.
        is_all_sample_consensus = True
        # Quality breadth positions are all be certain to be accurate.
        # General Stats quality breadth passes if all the following conditions for the position are true:
        # - Reference called and not duplicated.
        # - All analyses called and passed all filters.
        # - All samples have consensus within their aligner/snpcaller combinations.
        is_all_quality_breadth = True

        # A position is included in the missing data matrix if at least one analysis passes quality breadth and is a SNP.
        is_missing_matrix = False

        # position_stats is a counter across all SampleAnalyses at the current position. It used in the Matrix files.
        position_stats = Counter({
            # TODO: verify 'N' represents NoCall, AnyCall, Deletion, etc.
            # Tally of SampleAnalysis A/C/G/T calls where anything else is called N.
            # 'A': 0, 'C': 0, 'G': 0, 'T': 0, 'N': 0,
            #
            # Tally of SampleAnalyses with any base call. Excludes None (X) and Any (N) calls.
            # 'was_called': 0,
            #
            # Tally of SampleAnalyses with coverage/proportion at least as high as the threshold.
            # 'passed_coverage_filter': 0, 'passed_proportion_filter': 0
            #
            # Tally of SampleAnalyses where the call was a degenerate, matched, or differed from the reference call.
            # 'called_degen': 0, 'called_reference': 0, 'called_snp': 0
            #
            # The character at each position of the following filter strings indicates whether a corresponding SampleAnalysis
            # passed the filter:
            'CallWasMade': '',
            'PassedDepthFilter': '',
            'PassedProportionFilter': '',
            'Pattern': []
        })
        # pattern = []
        # pattern_append = pattern.append

        # TODO: document pattern legend
        # pattern_legend
        pattern_legend = {None: 1}
        if reference_position.simple_call == 'N':
            position_stats['Pattern'] = ['N']
        else:
            position_stats['Pattern'] = ['1']
            pattern_legend[reference_position.simple_call] = '1'


        # call_str is the base call for each SampleAnalysis starting with the reference.
        call_str = [reference_position.call]
        call_str_append = call_str.append

        # masked_call_str is the same as the call string except calls that did not pass the coverage/proportion filter are
        # masked out with 'N' indicating they did not pass.
        masked_call_str = [reference_position.call]

        # all_sample_stats is a list of sample_stats. It represents all the SampleAnalysis stats grouped by sample name.
        all_sample_stats = [
            [
                # any - True if true in any analysis_stats for any sample.
                Counter({
                    'was_called': 0,
                    'passed_coverage_filter': 0,
                    'passed_proportion_filter': 0,
                    'quality_breadth': 0,
                    'called_reference': 0,
                    'called_snp': 0,
                    'called_degen': 0
                }),
                # all - True if tru of all analysis_stats for all samples.
                Counter({
                    'was_called': 1,
                    'passed_coverage_filter': 1,
                    'passed_proportion_filter': 1,
                    'quality_breadth': 1,
                    'called_reference': 1,
                    'called_snp': 1,
                    'called_degen': 1
                })
            ]
        ]
        for sample in samples:
            # any - True if true in any of the analysis_stats for the same sample.
            any = Counter({
                'was_called': 0,
                'passed_coverage_filter': 0,
                'passed_proportion_filter': 0,
                'quality_breadth': 0,
                'called_reference': 0,
                'called_snp': 0,
                'called_degen': 0
            })
            # all - True if true in all of the analysis_stats for the same sample.
            all = Counter({
                'was_called': 1,
                'passed_coverage_filter': 1,
                'passed_proportion_filter': 1,
                'quality_breadth': 1,
                'called_reference': 1,
                'called_snp': 1,
                'called_degen': 1
            })
            # sample_stats is composed of analysis_stats dictionaries for each aligner/snpcaller used on the sample.
            # The first two entries are special in that they summarize the analysis_stats. They are using a tripwire approach
            # where the flag will toggle if the assumption fails.
            sample_stats = [any, all]

            # prev_analysis_call is used to detect sample consensus.
            prev_analysis_call = None
            for analysis in sample:
                # analysis_stats are unique to each SampleAnalysis. It is used in the Sample Statistics file.
                analysis_stats = Counter({
                    'was_called': 0,
                    'passed_coverage_filter': 0,
                    'passed_proportion_filter': 0,
                    'quality_breadth': 0,
                    'called_reference': 0,
                    'called_snp': 0,
                    'called_degen': 0
                })

                call_str_append(analysis.call)

                # FIXME: coverage/proportion may be "PASS" if the value is not deprecated in the VCF contig parser.
                # get_proportion/get_coverage

                # Check if the position passed the minimum coverage value set by the user.
                is_pass_coverage, pass_str = self._is_pass_filter(analysis.coverage, coverage_threshold)
                position_stats['PassedDepthFilter'] += pass_str
                if is_pass_coverage:
                    analysis_stats['passed_coverage_filter'] = 1
                    position_stats['passed_coverage_filter'] += 1
                else:
                    is_all_passed_coverage = False
                    is_all_quality_breadth = False

                # Check if the position passed the minimum proportion value set by the user.
                is_pass_proportion, pass_str = self._is_pass_filter(analysis.proportion, proportion_threshold)
                position_stats['PassedProportionFilter'] += pass_str
                if is_pass_proportion:
                    analysis_stats['passed_proportion_filter'] = 1
                    position_stats['passed_proportion_filter'] += 1
                else:
                    is_all_passed_proportion = False
                    is_all_quality_breadth = False

                # Check if all analyses for the same sample match.
                if prev_analysis_call is None:
                    prev_analysis_call = analysis.simple_call
                elif prev_analysis_call != analysis.simple_call:
                    is_all_sample_consensus = False
                    is_all_quality_breadth = False

                # A position is called if it was identified as one of A/C/G/T or a degeneracy.
                # X means no value, N means any value.
                is_called = True
                if analysis.call in ['X', 'N']:
                    position_stats['CallWasMade'] += 'N'
                    is_called = False
                    is_all_called = False
                    is_all_quality_breadth = False
                else:
                    analysis_stats['was_called'] = 1
                    position_stats['was_called'] += 1
                    position_stats['CallWasMade'] += 'Y'

                # Missing Data Matrix masks calls that did not pass a filter with 'N'
                # TODO: document that we are checking for was_called because we don't want to mask 'X' calls
                # TODO: Can this be better expressed?
                if not is_called or is_pass_coverage and is_pass_proportion:
                    masked_call_str.append(analysis.call)
                else:
                    masked_call_str.append('N')
                    is_all_sample_consensus = False
                    is_all_quality_breadth = False

                if analysis.simple_call == 'N':
                    is_all_sample_consensus = False
                    is_all_quality_breadth = False

                # TODO: document meaning/purpose of pattern
                # Patterns use numbers to show which analyses were called A/C/G/T and which samples had the same call value.
                if analysis.simple_call != 'N' and is_pass_coverage and is_pass_proportion:
                    # Each new base call encountered is assigned a the next higher number
                    if analysis.simple_call not in pattern_legend:
                        pattern_legend[None] += 1
                        pattern_legend[analysis.simple_call] = pattern_legend[None]
                    position_stats['Pattern'].append(str(pattern_legend[analysis.simple_call]))
                else:
                    position_stats['Pattern'].append('N')

                # Count the number of A/C/G/T calls. Any other value is N. See Position.simple_call().
                position_stats[analysis.simple_call] += 1

                # TODO: Clarify the purpose of this if statement.
                # Only count significant measurements.
                if is_called and is_pass_coverage and is_pass_proportion and reference_position.simple_call != 'N':
                    analysis_stats['quality_breadth'] = 1
                    # TODO: Should the first if be simple_call?
                    # if analysis.call in ['X', 'N']:
                    if analysis.simple_call == 'N':
                        position_stats['called_degen'] += 1
                        analysis_stats['called_degen'] = 1
                    elif analysis.call == reference_position.call:
                        position_stats['called_reference'] += 1
                        analysis_stats['called_reference'] = 1
                    elif dups_position.call != '1':
                        # Called A/C/G/T and doesn't match the reference.
                        position_stats['called_snp'] += 1
                        analysis_stats['called_snp'] = 1
                        is_missing_matrix = True

                    # Sample stats is a little stricter than the matrices on what passes.
                    if dups_position.call == '1':
                        analysis_stats['quality_breadth'] = 0
                        analysis_stats['called_degen'] = 0
                        analysis_stats['called_reference'] = 0
                        is_all_quality_breadth = False

                else:
                    is_all_quality_breadth = False

                sample_stats.append(analysis_stats)

            # Summarize the statistics for each sample where any or all of its SampleAnalysis combinations passed.
            # It is using a tripwire approach where the if statement toggles the flag if the assumption fails.
            # - any assumes all the stats failed
            # - all assumes all the stats passed
            for analysis_stats in sample_stats[2:]:
                for key, value in analysis_stats.items():
                    if value:
                        # any - The stat passed in at least one analysis_stat.
                        any[key] = 1
                        all_sample_stats[0][0][key] = 1
                    else:
                        # all - The stat failed in at least one analysis_stat.
                        all[key] = 0
                        all_sample_stats[0][1][key] = 0

            all_sample_stats.append(sample_stats)

        return PositionInfo(
            # General Stats
            is_all_called=is_all_called,
            is_reference_clean=is_reference_clean,
            is_reference_duplicated=is_reference_duplicated,
            is_all_passed_coverage=is_all_passed_coverage,
            is_all_passed_proportion=is_all_passed_proportion,
            is_all_passed_consensus=is_all_sample_consensus,
            is_all_quality_breadth=is_all_quality_breadth,
            is_best_snp=is_all_quality_breadth and position_stats['called_snp'] > 0,

            # NOTE: Would it increase performance if this were a tuple of tuples and we avoided using append?
            # Sample Stats - A list of list of Counters representing the stats for each analysis file grouped by sample.
            all_sample_stats=all_sample_stats,

            # Missing Data Matrix condition - at least one SampleAnalysis passes quality_breadth and is a SNP.
            is_missing_matrix=is_missing_matrix,

            # NASP Master Matrix
            # Counters
            called_reference=position_stats['called_reference'],
            called_snp=position_stats['called_snp'],
            passed_coverage_filter=position_stats['passed_coverage_filter'],
            passed_proportion_filter=position_stats['passed_proportion_filter'],
            num_A=position_stats['A'],
            num_C=position_stats['C'],
            num_G=position_stats['G'],
            num_T=position_stats['T'],
            num_N=position_stats['N'],
            # Strings
            call_str=call_str,
            masked_call_str=masked_call_str,
            CallWasMade=position_stats['CallWasMade'],
            PassedDepthFilter=position_stats['PassedDepthFilter'],
            PassedProportionFilter=position_stats['PassedProportionFilter'],
            Pattern=position_stats['Pattern']
        )

    # TODO: update method comment
    def analyze_contig(self, coroutine_fn, sample_groups, dups_contig, reference_contig):
        """
        analyze_contig expects reference_contig, dups_contig, and sample_analyses to represent the same contig from
        different sources.

        Args:
            coroutines (callable): A function that take a contig name and returns a tuple of coroutines that take Position tuples.
            reference_contig (FastaContig):
            dups_contig (FastaContig):
            sample_groups (tuple of SampleAnalysis tuples): SampleAnalyses grouped by sample name.

        Returns:
            (list of lists of dict, collections.Counter): SampleAnalysis stats grouped by sample name and contig stats.
        """
        # sample stats is a list of dict lists representing the SampleAnalysis stats in the same order as sample_groups.
        sample_stats = None
        contig_stats = Counter({'Contig': reference_contig.name})
        coroutines = coroutine_fn(reference_contig.name)

        # Initialize outfile coroutines. This will create the file, write the header, and wait for each line of data.
        for coroutine in coroutines:
            coroutine.send(None)

        contig_stats['reference_length'] = len(reference_contig)
        # FIXME: Ideally the Fasta.contigs generator should yield the same for both the reference and duplicates fastas.
        # The change that introduced sorting by length did not consistently result in an identical order. Calling get_contig on dups
        # was a quick fix. It also has the advantage that it will yield empty contigs if the contig does not exist. Perhaps a analyze_samples
        # could pass a generator that yields the contigs in the right order.
        for position in map(self.analyze_position, reference_contig.positions,
                            dups_contig.get_contig(reference_contig.name).positions,
                            self.sample_positions(reference_contig.name, sample_groups)):
            # contig_stats['reference_length'] += 1
            contig_stats['reference_clean'] += 1 if position.is_reference_clean else 0
            contig_stats['reference_duplicated'] += 1 if position.is_reference_duplicated else 0
            contig_stats['all_called'] += 1 if position.is_all_called else 0
            contig_stats['all_passed_coverage'] += 1 if position.is_all_passed_coverage else 0
            contig_stats['all_passed_proportion'] += 1 if position.is_all_passed_proportion else 0
            contig_stats['all_passed_consensus'] += 1 if position.is_all_passed_consensus else 0
            contig_stats['quality_breadth'] += 1 if position.is_all_quality_breadth else 0
            contig_stats['any_snps'] += 1 if position.called_snp > 0 else 0
            contig_stats['best_snps'] += 1 if position.is_best_snp else 0

            # Sum the SampleAnalysis stats preserving sample_groups order.
            if sample_stats is None:
                # The sample stats for the first position is copied.
                sample_stats = position.all_sample_stats
            else:
                # All following sample stats are summed with the first sample stat.
                for sum, analysis in zip(itertools.chain.from_iterable(sample_stats), itertools.chain.from_iterable(position.all_sample_stats)):
                    sum.update(analysis)

            for coroutine in coroutines:
                coroutine.send(position)

        return sample_stats, contig_stats