=======================================================================
:class:`passlib.hash.bigcrypt` - BigCrypt
=======================================================================

.. currentmodule:: passlib.hash

This class implements BigCrypt (a modified version of des-crypt) commonly
found on HP-UX, Digital Unix, and OSF/1. The main difference with
:class:`~passlib.hash.des_crypt` is that bigcrypt
uses all the characters of a password, not just the first 8,
and has a variable length hash string.

.. warning::

    This algorithm is dangerously weak, and should not be used if at all possible.

Usage
=====
This class can be used in exactly the same manner as :class:`~passlib.hash.des_crypt`.

Interface
=========
.. autoclass:: bigcrypt(checksum=None, salt=None, strict=False)

Format
======
An example hash (of the string ``passphrase``) is ``S/8NbAAlzbYO66hAa9XZyWy2``.
A bigcrypt hash string has the format :samp:`{salt}{checksum_1}{checksum_2...}{checksum_n}` for some integer :samp:`{n}>0`, where:

* :samp:`{salt}` is the salt, stored as a 2 character :func:`hash64 <passlib.utils.h64.encode_int12>`-encoded
  12-bit integer (``S/`` in the example).

* each :samp:`{checksum_i}` is a separate checksum, stored as an 11 character
  :func:`hash64 <passlib.utils.h64.encode_dc_int64>`-encoded 64-bit integer (``8NbAAlzbYO6`` and ``6hAa9XZyWy2``
  in the example).

* the integer :samp:`n` (the number of checksums) is determined by the formula
  :samp:`{n}=min(1, (len({secret})+7)//8)`.

.. rst-class:: html-toggle

Algorithm
=========
The bigcrypt algorithm is designed to re-use the original des-crypt algorithm:

1. Given a password string and a salt string.

2. The password is NULL padded at the end to the smallest non-zero multiple of 8 bytes.

3. The lower 7 bits of the first 8 characters of the password are used
   to form a 56-bit integer; with the first character providing
   the most significant 7 bits, and the 8th character providing
   the least significant 7 bits.

4. The 2 character salt string is decoded to a 12-bit integer salt value;
   The salt string uses little-endian
   :func:`hash64 <passlib.utils.h64.decode_int12>` encoding.

5. 25 repeated rounds of modified DES encryption are performed;
   starting with a null input block,
   and using the 56-bit integer from step 3 as the DES key.

   The salt is used to to mutate the normal DES encrypt operation
   by swapping bits :samp:`{i}` and :samp:`{i}+24` in the DES E-Box output
   if and only if bit :samp:`{i}` is set in the salt value.

6. The 64-bit result of the last round of step 5 is then
   lsb-padded with 2 zero bits.

7. The resulting 66-bit integer is encoded in big-endian order
   using the :func:`hash 64 <passlib.utils.h64.encode_int>` format.
   This forms the first checksum segment.

8. For each additional block of 8 bytes in the padded password (from step 2),
   an additional checksum is generated by repeating steps 3..7,
   with the following changes:

   a. Step 3 uses the specified 8 bytes of the password, instead of the first 8 bytes.
   b. Step 4 uses the first two characters from the previous checksum
      as the salt for the next checksum.

9. The final checksum string is the concatenation of the checksum segments
   generated from steps 7 and 8, in order.

.. note::

    Because of the chained structure, bigcrypt has the property that
    the first 13 characters of any bigcrypt hash form a valid :class:`~passlib.hash.des_crypt`
    hash of the same password; and bigcrypt hashes of any passwords
    less than 9 characters will be identical to des-crypt.

Security Issues
===============
BigCrypt is dangerously flawed:

* It suffers from all the flaws of :class:`~passlib.hash.des_crypt`.

* Since checksum in it's hash is essentially a separate
  des-crypt checksum, they can be attacked in parallel.

* It reveals information about the length of the encoded
  password (to within 8 characters), further reducing the keyspace that needs
  to be searched for each of the invididual segments.

* The last checksum typically contains only a few
  characters of the passphrase, and once cracked,
  can be used to narrow the overall keyspace.

Deviations
==========
This implementation of bigcrypt differs from others in two ways:

* Maximum Password Size:

  This implementation currently accepts arbitrarily large passwords,
  producing arbitrarily large hashes. Other implementation have
  various limits on maximum password length (commonly, 128 chars),
  and discard the remaining part of the password.

  Thus, while PassLib should be able to verify all existing
  bigcrypt hashes, other systems may require hashes generated by PassLib
  to be truncated to their specific maximum length.

* Unicode Policy:

  The original bigcrypt algorithm was designed for 7-bit ``us-ascii`` encoding only
  (as evidenced by the fact that it discards the 8th bit of all password bytes).

  In order to provide support for unicode strings,
  PassLib will encode unicode passwords using ``utf-8``
  before running them through bigcrypt. If a different
  encoding is desired by an application, the password should be encoded
  before handing it to PassLib.

.. rubric:: Footnotes

.. [#] discussion of bigcrypt & crypt16 -
       `<http://www.mail-archive.com/exim-dev@exim.org/msg00970.html>`_
