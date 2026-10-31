import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch
import importlib.util
spec = importlib.util.spec_from_file_location('integrated_offload', Path(__file__).resolve().parents[1] / '02_custom/s10_xcpd_integrated_qc/offload_completed.py')
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)

class OffloadTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        base=Path(self.temp.name);self.root=base/'local';self.external=base/'external'
        (self.root/'continuous5/cases').mkdir(parents=True);self.external.mkdir()
        self.sub='ADNI999S9999';self.ptid='999_S_9999';self.pair='EPI_20190507_MT1_20190506'
        self.runtime=self.root/'runs'/self.sub;self.source=self.root/'results'/self.ptid/self.pair
        self.source.mkdir(parents=True)
        identity={}
        for stage in ['mriqc','fmriprep']:
            outputs=self.runtime/'derivatives'/stage;outputs.mkdir(parents=True)
            (outputs/'영상.nii.gz').write_bytes(b'image-data-'+stage.encode())
            (outputs/'empty-directory').mkdir();(outputs/'relative-link').symlink_to('영상.nii.gz')
            shutil.copytree(outputs,self.source/stage,symlinks=True)
            record={'status':'execution_completed_QC_required','exit_code':0,'input_unchanged':True,'started_at':'2026-10-31T00:00:00Z','runner_sha256':'test','image':{'resolved':'test-image'}}
            folder=self.runtime/'logs'/('x_'+stage+'_sub-'+self.sub+'_ses-M138');folder.mkdir(parents=True)
            (folder/'run.json').write_text(json.dumps(record));identity[stage]={k:record[k] for k in ['started_at','runner_sha256','image']}
        (self.runtime/'work').mkdir();(self.runtime/'work/cache.bin').write_bytes(b'reproducible-cache')
        (self.runtime/'derivatives/.DS_Store').write_bytes(b'finder-metadata')
        (self.root/'continuous5/cases'/self.sub).mkdir();(self.root/'continuous5/cases'/self.sub/'config.yaml').write_text('source config')
        (self.root/'bids'/('sub-'+self.sub)).mkdir(parents=True)
        (self.root/'bids'/('sub-'+self.sub)/'input.nii.gz').write_bytes(b'input')
        (self.source/'pair_metadata.json').write_text(json.dumps({'subject':self.sub,'ptid':self.ptid,'pair_id':self.pair,'delivery_status':'processing_complete_QC_pending','execution_identity':identity}))
        (self.source/'.DS_Store').write_bytes(b'published-finder-metadata')
        self.a=m.Offloader(self.root,{'mount':str(self.external),'destination':str(self.external/'ADNI_SB'),'volume_uuid':'test','thread_id':'test','external_reserve_gib':0},volume_check=lambda:None)

    def test_verified_move_preserves_contents_links_paths_and_cache(self):
        receipt=self.a.archive(self.source)
        target=Path(receipt['external_path'])
        self.assertEqual(receipt['status'],'archived_and_local_space_reclaimed')
        self.assertTrue(self.runtime.is_symlink());self.assertTrue(self.source.is_symlink())
        self.assertEqual((self.runtime/'work/cache.bin').read_bytes(),b'reproducible-cache')
        self.assertEqual((self.source/'fmriprep/relative-link').read_bytes(),b'image-data-fmriprep')
        self.assertEqual((self.runtime/'derivatives/fmriprep/영상.nii.gz').read_bytes(),b'image-data-fmriprep')
        self.assertEqual((self.runtime/'derivatives/.DS_Store').read_bytes(),b'finder-metadata')
        self.assertEqual((self.source/'.DS_Store').read_bytes(),b'published-finder-metadata')
        self.assertTrue((target/'fmriprep/empty-directory').is_dir())
        self.assertTrue((target/'archive_manifest.json').is_file())
        self.assertFalse(list(self.root.rglob('*.offload-verified-*')))
        self.assertEqual(self.a.archive(self.source)['status'],'archived_and_local_space_reclaimed')

    def test_partial_corrupted_copy_is_repaired_on_retry(self):
        original=m.copy_tree
        def corrupt(src,dst):
            original(src,dst)
            if Path(src).name=='fmriprep':(Path(dst)/'영상.nii.gz').write_bytes(b'corrupt')
        with patch.object(m,'copy_tree',side_effect=corrupt):
            with self.assertRaises(ValueError):self.a.archive(self.source)
        self.assertEqual(self.a.archive(self.source)['status'],'archived_and_local_space_reclaimed')

    def test_unicode_canonical_names_compare_equally(self):
        a=Path(self.temp.name)/'unicode-a';b=Path(self.temp.name)/'unicode-b';a.mkdir();b.mkdir()
        (a/'영상').write_bytes(b'same')
        import unicodedata
        (b/unicodedata.normalize('NFD','영상')).write_bytes(b'same')
        self.assertEqual(m.inventory(a),m.inventory(b))

    def test_active_subject_and_incomplete_stage_are_never_moved(self):
        with self.assertRaises(ValueError):self.a.archive(self.source,{self.sub})
        p=next((self.runtime/'logs').glob('*fmriprep*/run.json'));record=json.loads(p.read_text());record['status']='running';p.write_text(json.dumps(record))
        with self.assertRaises(ValueError):self.a.archive(self.source)
        self.assertFalse(self.runtime.is_symlink());self.assertTrue((self.runtime/'work/cache.bin').exists())

    def test_corrupted_copy_preserves_all_local_data(self):
        original=m.copy_tree
        def corrupt(src,dst):
            original(src,dst)
            if Path(src).name=='fmriprep':(Path(dst)/'영상.nii.gz').write_bytes(b'corrupt')
        with patch.object(m,'copy_tree',side_effect=corrupt):
            with self.assertRaises(ValueError):self.a.archive(self.source)
        self.assertFalse(self.runtime.is_symlink());self.assertFalse(self.source.is_symlink())
        self.assertEqual((self.runtime/'derivatives/fmriprep/영상.nii.gz').read_bytes(),b'image-data-fmriprep')

    def test_cleanup_failure_can_resume_without_copying_or_losing_data(self):
        with patch.object(m.shutil,'rmtree',side_effect=RuntimeError('simulated interruption')):
            with self.assertRaises(RuntimeError):self.a.archive(self.source)
        self.assertTrue(self.runtime.is_symlink())
        self.assertTrue((self.runtime/'work/cache.bin').is_file())
        with patch.object(m,'copy_tree',side_effect=AssertionError('should not recopy verified archive')):
            receipt=self.a.archive(self.source)
        self.assertEqual(receipt['status'],'archived_and_local_space_reclaimed')

    def test_volume_failure_and_destination_conflict_preserve_sources(self):
        self.a.check_volume=lambda:(_ for _ in ()).throw(RuntimeError('disconnected'))
        with self.assertRaises(RuntimeError):self.a.archive(self.source)
        self.a.check_volume=lambda:None
        target=self.a.dest/self.ptid/self.pair;target.mkdir(parents=True);(target/'other').write_text('preexisting')
        with self.assertRaises(ValueError):self.a.archive(self.source)
        self.assertFalse(self.runtime.is_symlink());self.assertEqual((target/'other').read_text(),'preexisting')

    def test_postprocessing_gate_keeps_local_until_validated(self):
        self.a.settings.update(require_postprocessing=True,postprocessing_config_id='fixture')
        with self.assertRaisesRegex(ValueError,'Waiting for S8'):self.a.archive(self.source)
        self.assertFalse(self.source.is_symlink())
        stage=self.source/'s10/fixture';stage.mkdir(parents=True)
        pre=stage/'pre_qc.json';m.save(pre,{'status':'fail'})
        ready={'status':'postprocessing_complete_final_QC_pending','subject':self.sub,'config_id':'fixture',
               'runs':[{'pre_xcpd_qc_status':'fail','xcpd_status':'skipped_pre_qc_fail'}],
               'evidence':{'s10/fixture/pre_qc.json':m.sha(pre)}}
        m.save(stage/'archive_ready.json',ready)
        self.assertEqual(self.a.archive(self.source)['status'],'archived_and_local_space_reclaimed')

    def test_failed_or_tampered_postprocessing_not_archived(self):
        self.a.settings.update(require_postprocessing=True,postprocessing_config_id='fixture')
        stage=self.source/'s10/fixture';stage.mkdir(parents=True)
        pre=stage/'pre_qc.json';m.save(pre,{'status':'pending'})
        ready={'status':'postprocessing_complete_final_QC_pending','subject':self.sub,'config_id':'fixture',
               'runs':[{'pre_xcpd_qc_status':'review_required','xcpd_status':'partial','functional_outputs_valid':False}],
               'evidence':{'s10/fixture/pre_qc.json':m.sha(pre)}}
        m.save(stage/'archive_ready.json',ready)
        with self.assertRaisesRegex(ValueError,'did not finish'):self.a.archive(self.source)
        ready['runs'][0].update(xcpd_status='success',functional_outputs_valid=True)
        m.save(stage/'archive_ready.json',ready);pre.write_text('changed')
        with self.assertRaisesRegex(ValueError,'evidence changed'):self.a.archive(self.source)

if __name__=='__main__':unittest.main()
