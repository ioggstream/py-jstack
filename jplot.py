"""
    plot java heap usage by class

    ex. a simple ipython usage pattern:
    # gather some data from your vm
    while sleep 5; do
       jmap -histo $(pidof java) > /tmp/histo.$(date -I)
    done

   # process files 
   files = !ls /tmp/histo.*
   H = jhisto(files, limit=30)

   # plot the graph
   plot_classes(H, limit=10)

"""
RANK, COUNT, BYTES, CLASS = 0, 1, 2, 3


def dictize(stream, limit=None):
    """parse the jmap -hist files and returns a dict
       @param stream - the jmap -histo output
       @param limit - get only the first limit lines,
                      default: None -> all
    """
    d = {}
    # input is
    ret = [x.split() for x in stream.readlines()[3:-1]]
    for (rank, count, n_bytes, cls) in ret[:limit]:
        d[cls] = (count, n_bytes)
    return d


def vdiff(v1, v2):
    """A simple vectorial difference"""
    return tuple((float(i) - float(j)) for i, j in zip(v1, v2))


def jhisto(files, delta=True, limit=20):
    """Create an object count table
       @param delta - if true, counters start at the values
                      contained in the first file

       @return a dict of the following form {
                 'cls_1': [ (#instances, #mem), (#instances, #mem), ... ],
                 'cls_2': [ (#instances, #mem), (#instances, #mem), ... ],
               }
    """
    start = {}
    tot = {}
    for f in files:
        # parse file
        with open(f) as fd:
            d = dictize(fd, limit)
            if delta:
                start = d
                delta = False
        # append data
        for k in d:
            tot.setdefault(k, [])
            diff = vdiff(d[k], start.get(k, (0, 0)))
            tot[k].append(diff)
    return tot


def plot_classes(table, limit=10, fontsize=10):
    """Plots the memory usage of the top 10 classes
       @param table - a jhisto-generated file
       @param limit - how many class to trace
       @param fontsize - font size on the legend
    """
    from matplotlib import pyplot as plt
    # v is a list of vector, take the higher value
    table_max = {k: max([i[1] for i in v]) for k, v in table.items()}
    top = sorted(table_max, key=lambda x: table_max[x])[-limit:]
    for k in top:
        # table[k] = [ (a1,a2), (b1,b2), (c1,c2)]
        # zip* trasposes to: [ (a1, b1, c1, ...), (a2, b2, c2), .. ]
        # skip the first count #instances
        cls, mem = zip(*table[k])
        plt.plot(mem, label=k)
    #show legend
    plt.legend(loc='lower left', prop={'size': fontsize})
    plt.show()
