from __future__ import absolute_import

from . import overlap_module


def retrieve_key(line, key):
    key += '='
    if key in line:
        if ";{}".format(key) in line:
            item = line.strip().split( ";{}".format(key) )[-1].split(";")[0].split("\t")[0]

        elif "\t{}".format(key) in line:
            item = line.strip().split( "\t{}".format(key) )[-1].split(";")[0].split("\t")[0]
        else:
            return False

    return item

#Check if no merging should occur
def skip_variant(chrA,chrB,type_A,type_B,vcf_line_A,vcf_line_B,pass_only,current_variant,analysed_variants,no_var):
    #The variant is already clustered/analysed
    if current_variant in analysed_variants:
       return True

    # only treat variants on the same pair of chromosomes
    if chrA != chrB:
       return True

    # dont merge variants of different type
    if type_A != type_B and not no_var:
       return True

    # if the pass_only option is chosen, only variants marked PASS will be merged
    if pass_only:
       filter_tag = vcf_line_B[6]
       if filter_tag not in ['PASS', '.']:
           return True


#Collect SAMPLE columns from all merged variants:
def collect_sample(vcf_line,samples,sample_order,f):
    variant=vcf_line[2].replace(";","_").replace(":","_").replace("|","_")
    sample_data=[variant]

    for sample in samples:
        if not sample in sample_order:
           continue
        if not f in sample_order[sample]:
           continue
        sample_position = sample_order[sample][f]

        entries = vcf_line[8].split(":")
        sample_entries = vcf_line[9 + sample_position].split(":")
        sample_data.append(sample)
        for i, entry in enumerate(entries):
            sample_data.append("{}:{}".format( entry,sample_entries[i] ) )

    return "|".join(sample_data).replace(",",":")

#collect INFO from all merged_variants
def collect_info(vcf_line):
    INFO = vcf_line[7]
    INFO_content = INFO.split(";")
    variant=vcf_line[2].replace(";","_").replace(":","_").replace("|","_")
    all_info=[variant]

    for content in INFO_content:
        tag = content.split("=")[0]
        if not ":" in content and not "|" in content:
           all_info.append( content.replace("=",":").replace(",",":") )

    return "|".join(all_info)

#create a GATK-like set of all merged variants
def determine_set_tag(priority_order, files):
    n_filtered = 0
    n_pass = 0

    filtered = []
    for sample in priority_order:
        file = files.get(sample, None)
        if file is None:
            continue
        if file.split('\t')[6] in ['PASS', '.']:
            n_pass += 1
        else:
            n_filtered += 1
    if n_pass == len(priority_order):
        return "Intersection"
    elif n_filtered == len(priority_order):
        return "FilteredInAll"
    else:
        for sample in priority_order:
            if sample not in files:
                continue
            elif files[sample].split('\t')[6] in ['PASS', '.']:
                filtered.append(sample)
            else:
                filtered.append("filterIn" + sample)
        return "-".join(filtered)

#merge csq field of merged variants (for instance when merging BNDs)
def merge_csq(info, csq):
    """Merge the csq fields of bnd variants"""
    var_csq = info.split("CSQ=")[-1].split(";")[0]
    csq.append(var_csq)
    effects = set([])
    for csq_field in csq:
        effects = effects | set(csq_field.split(","))
    CSQ = "CSQ=" + ",".join(list(effects))
    pre_CSQ = info.split("CSQ=")[0]
    post_CSQ = info.split("CSQ=")[-1].split(";")
    if len(post_CSQ) == 1:
        post_CSQ = ""
    else:
        post_CSQ = ";" + ";".join(post_CSQ[1:])

    return pre_CSQ + CSQ + post_CSQ


def sort_format_field(line, samples, sample_order, sample_print_order, priority_order, files, representing_file, args):
    format_columns = {}
    format_entries = []
    format_entry_length = []

    if not args.same_order:
        for input_file in priority_order:
            if input_file not in files:
                continue
            for sample in sorted(samples):
                if sample not in format_columns and input_file in sample_order[sample]:

                    vcf_line = files[input_file].strip().split("\t")
                    sample_position = sample_order[sample][input_file]
                    format_columns[sample] = {}
                    entries = vcf_line[8].split(":")
                    sample_entries = vcf_line[9 + sample_position].split(":")

                    for i, entry in enumerate(entries):
                        format_columns[sample][entry] = sample_entries[i]
                        if entry not in format_entries:
                            n = sample_entries[i].count(",")
                            format_entries.append(entry)
                            format_entry_length.append(n)

        if len(line) > 8:
            format_string = []
            line[8] = ":".join(format_entries)
            del line[9:]
            for sample in samples:
                format_string = []
                for entry in format_entries:
                    j = 0
                    if sample in format_columns:
                        if entry in format_columns[sample]:
                            format_string.append(format_columns[sample][entry])
                        elif entry == "GT":
                            format_string.append("./.")
                        else:
                            sub_entry = []
                            for i in range(format_entry_length[j] + 1):
                                sub_entry.append(".")
                            format_string.append(",".join(sub_entry))
                    else:
                        if entry == "GT":
                            format_string.append("./.")
                        else:
                            sub_entry = []
                            for i in range(format_entry_length[j] + 1):
                                sub_entry.append(".")
                            format_string.append(",".join(sub_entry))
                    j += 1

                line.append(":".join(format_string))

    # generate a union of the info fields
    info_union = []
    tags_in_info = []

    # tags only to be copied from the file with highest priority (to avoid problems in downstream analyses
    blacklist=set(["SVLEN","END","SVTYPE"])

    first=True
    for input_file in priority_order:
        if input_file not in files:
            continue

        INFO = files[input_file].strip().split("\t")[7]
        INFO_content = INFO.split(";")

        for content in INFO_content:
            tag = content.split("=")[0]

            if not first and tag in blacklist:
                continue

            if tag not in tags_in_info:
                tags_in_info.append(tag)
                info_union.append(content)

        first=False

    new_info = ";".join(info_union)
    line[7] = new_info
    return line


def merge(chromosome, variants, samples, sample_order, sample_print_order, priority_order, args):
    overlap_param = args.overlap
    bnd_distance = args.bnd_distance
    ins_distance=args.ins_distance
    no_intra = args.no_intra
    no_var = args.no_var
    pass_only = args.pass_only

    # search for similar variants
    to_be_printed = {}
    analysed_variants = set([])
    for i in range(len(variants)):
        if i in analysed_variants:
            continue

        merge = []
        #keep track of all csq of merged variants
        csq = []

        #Keep track of all files in the cluster
        files = {}
        #keep track of the FILTER column of all merged files
        filters_tag = {}
        #keep track of SAMPLEs columns of all merged files
        samples_tag = {}
        #keep track of INFO column of all merged files
        info_tag = {}
        #quality
        qual_tag = {}
        #pos
        pos_tag = {}
        #chrom
        chrom_tag ={}

        if args.priority:
            id=variants[i][-3]
        else:
            id=variants[i][-3].split(".vcf")[0].split("/")[-1]

        vcf_line_A=variants[i][-1].strip().split("\t")
        chrom_tag[id]=[ "{}|{}".format(vcf_line_A[2].replace(";","_").replace(":","_").replace("|","_"),vcf_line_A[0]) ]
        pos_tag[id]=[ "{}|{}".format(vcf_line_A[2].replace(";","_").replace(":","_").replace("|","_"),vcf_line_A[1]) ]
        qual_tag[id]=[ "{}|{}".format(vcf_line_A[2].replace(";","_").replace(":","_").replace("|","_"),vcf_line_A[5]) ]
        filters_tag[id]=[ "{}|{}".format(vcf_line_A[2].replace(";","_").replace(":","_").replace("|","_"),vcf_line_A[6]) ]
        samples_tag[id]=[collect_sample( vcf_line_A ,samples,sample_order,id)]
        info_tag[id]=[collect_info(vcf_line_A)]

        for j in range(i + 1, len(variants)):
            vcf_line_B=variants[j][-1].strip().split("\t")

            # if the pass_only option is chosen, only variants marked PASS will be merged
            if pass_only:
                filter_tag = vcf_line_A[6]
                if filter_tag not in ['PASS', '.']:
                    break

            if skip_variant(variants[i][0],variants[j][0],variants[i][1],variants[j][1],vcf_line_A,vcf_line_B,pass_only,j,analysed_variants,no_var):
                continue

            # if no_intra is chosen, variants may only be merged if they belong to different input files
            if no_intra and variants[i][-3] == variants[j][-3]:
                continue

            if "INS" in variants[i][1]:
                overlap, match = overlap_module.variant_overlap(
                    chromosome, variants[i][0], variants[i][2], variants[i][3], variants[j][2], variants[j][3], -1, ins_distance)

            else:
                overlap, match = overlap_module.variant_overlap(
                    chromosome, variants[i][0], variants[i][2], variants[i][3], variants[j][2], variants[j][3], overlap_param, bnd_distance)

            if match:
                # add similar variants to the merge list and remove them
                if args.priority:
                    match_id=variants[j][-3]
                else:
                    match_id=variants[j][-3].split(".vcf")[0].split("/")[-1]

                files[match_id] = variants[j][-1]
                merge.append(vcf_line_B[2].replace(";", "_") + ":" + match_id)
                if not match_id in filters_tag:
                    filters_tag[match_id]=[]
                    samples_tag[match_id]=[]
                    info_tag[match_id]=[]
                    chrom_tag[match_id]=[]
                    pos_tag[match_id]=[]
                    qual_tag[match_id]=[]

                chrom_tag[match_id].append("{}|{}".format(vcf_line_B[2].replace(";","_").replace(":","_").replace("|","_"),variants[j][-1].split("\t")[0]) )
                pos_tag[match_id].append("{}|{}".format(vcf_line_B[2].replace(";","_").replace(":","_").replace("|","_"),variants[j][-1].split("\t")[1]) )
                qual_tag[match_id].append("{}|{}".format(vcf_line_B[2].replace(";","_").replace(":","_").replace("|","_"),variants[j][-1].split("\t")[5]) )
                filters_tag[match_id].append("{}|{}".format(vcf_line_B[2].replace(";","_").replace(":","_").replace("|","_"),variants[j][-1].split("\t")[6]) )

                samples_tag[match_id].append(collect_sample(vcf_line_B ,samples,sample_order,match_id))
                info_tag[match_id].append( collect_info(vcf_line_B) )

                if variants[i][0] != chromosome and "CSQ=" in variants[j][-1]:
                    info = vcf_line_B[7]
                    csq.append(info.split("CSQ=")[-1].split(";")[0])
                analysed_variants.add(j)

        line = vcf_line_A

        if csq:
            line[7] = merge_csq(line[7], csq)
        if not line[0] in to_be_printed:
            to_be_printed[line[0]] = []

        if args.priority:
            files[variants[i][-3]] = "\t".join(line)
            representing_file = variants[i][-3]
        else:
            files[variants[i]
                    [-3].split(".vcf")[0].split("/")[-1]] = "\t".join(line)
            representing_file = variants[i][-3].split(".vcf")[
                0].split("/")[-1]
        line = sort_format_field(
            line, samples, sample_order, sample_print_order, priority_order, files, representing_file, args)
        if merge and not args.notag:
            line[7] += ";VARID=" + "|".join(merge)
            line[2] += ":{}|".format(variants[i][-3].split(".vcf")
                                        [0].split("/")[-1]) + "|".join(merge)
        if not args.notag:
            set_tag = determine_set_tag(priority_order, files)
            line[7] += ";set={}".format(set_tag)
            line[7] += ";FOUNDBY={}".format( len(set(filters_tag.keys())) )

        #add chrom information of all merged variants
        callers=[]
        for tag in filters_tag:
            line[7]+=";{}_CHROM={}".format(tag,",".join(chrom_tag[tag]))
            callers.append(tag)
        #add pos information of all merged variants
        for tag in filters_tag:
            line[7]+=";{}_POS={}".format(tag,",".join(pos_tag[tag]))
        #add qual information of all merged variants
        for tag in filters_tag:
            line[7]+=";{}_QUAL={}".format(tag,",".join(qual_tag[tag]))
        #add filter of all merged variants
        for tag in filters_tag:
            line[7]+=";{}_FILTERS={}".format(tag,",".join(filters_tag[tag]).replace(";",","))
        #add samples information for all merged variants
        for tag in samples_tag:
            line[7]+=";{}_SAMPLE={}".format(tag,",".join(samples_tag[tag]))
        #add info column for all merged variants
        for tag in samples_tag:
            line[7]+=";{}_INFO={}".format(tag,",".join(info_tag[tag]))

        if not args.notag:
            line[7]+=";svdb_origin={}".format("|".join(callers))

        sup_vec=[]
        for c in sorted(priority_order):
            if c in filters_tag:
                sup_vec.append("1") 
            else:
                sup_vec.append("0") 

        line[7]+=";SUPP_VEC={}".format("".join(sup_vec))

        to_be_printed[line[0]].append(line)

        analysed_variants.add(i)

    return to_be_printed
