# _base_ = [
#     # '_base_/default_runtime.py',
#     # '_base_/datasets/potsdam.py'
# ]

from mmpretrain.models.backbones import ViTEVA02

max_epochs = 100

batch_size = 16
num_workers = batch_size
start_lr = 0.01
val_interval = 5

custom_imports = dict(
    imports=["mmdet.models", "mmpretrain.models"], allow_failed_imports=False
)


# model settings
norm_cfg = dict(type="SyncBN", requires_grad=True)
crop_size = (512, 512)
data_preprocessor = dict(
    type="SegDataPreProcessor",
    mean=[123.675, 116.28, 103.53],
    std=[58.395, 57.12, 57.375],
    bgr_to_rgb=True,
    pad_val=0,
    seg_pad_val=255,
    size=crop_size,
    test_cfg=dict(size_divisor=32),
)
num_classes = 6

checkpoint = "https://download.openmmlab.com/mmpretrain/v1.0/eva02/eva02-tiny-p14_pre_in21k_20230505-d703e7b1.pth"  # noqa

model = dict(
    type="EncoderDecoder",
    data_preprocessor=data_preprocessor,
    #! mmpretrain.models.backbones.vision_transformer
    backbone=dict(
        type=ViTEVA02,
        arch="tiny",
        # embed_dims=2048,
        img_size=crop_size,
        patch_size=14,
        final_norm=False,
        out_type="featmap",
        out_indices=(0, 1, 2, 3),
        init_cfg=dict(type="Pretrained", checkpoint=checkpoint, prefix="backbone."),
    ),
    decode_head=dict(
        type="ASPPHead",
        in_channels=192,
        channels=512,
        dilations=(1, 12, 24, 36),
        dropout_ratio=0.1,
        num_classes=num_classes,
        norm_cfg=norm_cfg,
        align_corners=False,
        loss_decode=dict(type="CrossEntropyLoss", use_sigmoid=False, loss_weight=1.0),
    ),
    auxiliary_head=dict(
        type="FCNHead",
        in_channels=192,
        in_index=2,
        channels=256,
        num_convs=1,
        concat_input=False,
        dropout_ratio=0.1,
        num_classes=num_classes,
        norm_cfg=norm_cfg,
        align_corners=False,
        loss_decode=dict(type="CrossEntropyLoss", use_sigmoid=False, loss_weight=0.4),
    ),
    # model training and testing settings
    train_cfg=dict(),
    test_cfg=dict(mode="whole"),
)


# dataset settings
dataset_type = "PotsdamDataset"
data_root = "data/potsdam"

train_pipeline = [
    dict(type="LoadImageFromFile"),
    dict(type="LoadAnnotations", reduce_zero_label=True),
    dict(
        type="RandomResize", scale=(512, 512), ratio_range=(0.5, 2.0), keep_ratio=True
    ),
    dict(type="RandomCrop", crop_size=crop_size, cat_max_ratio=0.75),
    dict(type="RandomFlip", prob=0.5),
    dict(type="PhotoMetricDistortion"),
    dict(type="PackSegInputs"),
]
test_pipeline = [
    dict(type="LoadImageFromFile"),
    dict(type="Resize", scale=(512, 512), keep_ratio=True),
    # add loading annotation after ``Resize`` because ground truth
    # does not need to do resize data transform
    dict(type="LoadAnnotations", reduce_zero_label=True),
    dict(type="PackSegInputs"),
]


img_ratios = [0.5, 0.75, 1.0, 1.25, 1.5, 1.75]
tta_pipeline = [
    dict(type="LoadImageFromFile", backend_args=None),
    dict(
        type="TestTimeAug",
        transforms=[
            [dict(type="Resize", scale_factor=r, keep_ratio=True) for r in img_ratios],
            [
                dict(type="RandomFlip", prob=0.0, direction="horizontal"),
                dict(type="RandomFlip", prob=1.0, direction="horizontal"),
            ],
            [dict(type="LoadAnnotations")],
            [dict(type="PackSegInputs")],
        ],
    ),
]
train_dataloader = dict(
    batch_size=batch_size,
    num_workers=num_workers,
    persistent_workers=True,
    # sampler=dict(type='InfiniteSampler', shuffle=True),
    # ! it's important to slove "Been training on the first Epoch"
    sampler=dict(type="DefaultSampler", shuffle=True),
    dataset=dict(
        type=dataset_type,
        data_root=data_root,
        data_prefix=dict(img_path="img_dir/train", seg_map_path="ann_dir/train"),
        pipeline=train_pipeline,
    ),
)
val_dataloader = dict(
    batch_size=batch_size,
    num_workers=num_workers,
    persistent_workers=True,
    sampler=dict(type="DefaultSampler", shuffle=False),
    dataset=dict(
        type=dataset_type,
        data_root=data_root,
        data_prefix=dict(img_path="img_dir/val", seg_map_path="ann_dir/val"),
        pipeline=test_pipeline,
    ),
)
test_dataloader = val_dataloader

val_evaluator = dict(type="IoUMetric", iou_metrics=["mIoU", "mDice", "mFscore"])

test_evaluator = val_evaluator

# optimizer
embed_multi = dict(lr_mult=1.0, decay_mult=0.0)
optimizer = dict(
    type="AdamW", lr=0.0001, weight_decay=0.05, eps=1e-8, betas=(0.9, 0.999)
)


optim_wrapper = dict(
    type="OptimWrapper",
    # optimizer=dict(type='SGD', lr=0.02, momentum=0.9, weight_decay=0.0001)
    # optimizer=dict(type='Adam', lr=0.005, weight_decay=0.0001)
    optimizer=dict(
        type="Adam",
        lr=start_lr,
        weight_decay=1e-2,
    ),
)


# learning policy
param_scheduler = [
    dict(type="LinearLR", start_factor=start_lr, by_epoch=False, begin=0, end=1),
    dict(
        type="CosineAnnealingLR",
        by_epoch=True,
        begin=1,
        T_max=max_epochs,
        end=max_epochs,
    ),
]

# training schedule for 160k
train_cfg = dict(
    type="EpochBasedTrainLoop", max_epochs=max_epochs, val_interval=val_interval
)
val_cfg = dict(type="ValLoop")
test_cfg = dict(type="TestLoop")
default_hooks = dict(
    timer=dict(type="IterTimerHook"),
    logger=dict(type="LoggerHook", interval=500, log_metric_by_epoch=True),
    param_scheduler=dict(type="ParamSchedulerHook"),
    checkpoint=dict(
        type="CheckpointHook",
        by_epoch=True,
        interval=1,
        max_keep_ckpts=5,
        save_best="mIoU",
    ),
    sampler_seed=dict(type="DistSamplerSeedHook"),
    visualization=dict(type="SegVisualizationHook"),
)

# Default setting for scaling LR automatically
#   - `enable` means enable scaling LR automatically
#       or not by default.
#   - `base_batch_size` = (8 GPUs) x (2 samples per GPU).
auto_scale_lr = dict(enable=False, base_batch_size=16)


# Modify from default_runtime.py
default_scope = "mmseg"
env_cfg = dict(
    cudnn_benchmark=True,
    mp_cfg=dict(mp_start_method="fork", opencv_num_threads=0),
    dist_cfg=dict(backend="nccl"),
)
# vis_backends = [dict(type='LocalVisBackend')]
vis_backends = [
    dict(type="LocalVisBackend"),
    # dict(type='WandbVisBackend',
    #      init_kwargs=dict(
    #          project='pure-seg',
    #          name=f'deeplabv3+_eva02-small_lr={start_lr}_{dataset_type}_{max_epochs}e',
    #          group='deeplabv3+',
    #          tags=['deeplabv3+', 'eva02', 'potsdam'],
    #          #  resume=True
    #      )
    #      )
]
visualizer = dict(
    type="SegLocalVisualizer", vis_backends=vis_backends, name="visualizer"
)
log_processor = dict(by_epoch=True)
log_level = "INFO"
load_from = None
resume = False

tta_model = dict(type="SegTTAModel")
